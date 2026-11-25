import copy
import random
from pathlib import Path

import numpy as np
import pytest
import torch
from torch import nn

from app.services.segmentation.model import SmallUNet3D
from training import checkpoint as cp
from training.dataset import SingleCaseCache
from training.sampling import PatchSampler
from training.tests.test_dataset import make_cohort, index_for


def test_historical_checkpoint_strict_compatibility_without_forward(monkeypatch):
    path = Path(__file__).resolve().parents[3] / "model/vascuai_model_handoff_for_codex_20261016/vascuai_model_handoff_recovered/model/artery_unet_10case_weighted_step700.pt"
    if not path.is_file(): pytest.skip("Optional preserved historical checkpoint unavailable")
    before = cp.digest(path)
    monkeypatch.setattr(SmallUNet3D, "forward", lambda *a: pytest.fail("Compatibility must not run inference"))
    result = cp.initialize_weights(SmallUNet3D(base=8), path, cp.HISTORICAL_SHA256, list(range(251, 261)))
    assert result["new_global_step"] == 0 and result["historical_recorded_step"] == 700
    assert cp.digest(path) == before == cp.HISTORICAL_SHA256


def test_initialization_rejects_hash_mismatch_and_validation_ids(tmp_path):
    model = SmallUNet3D(base=8)
    path = tmp_path / "legacy.pt"
    torch.save({"base_channels": 8, "patch_size": (64, 64, 64), "training_case_ids": [851],
                "model_state_dict": model.state_dict(), "step": 700}, path)
    with pytest.raises(cp.CheckpointError, match="SHA-256"):
        cp.initialize_weights(model, path, "0" * 64, [251])
    with pytest.raises(cp.CheckpointError, match="non-Training"):
        cp.initialize_weights(model, path, cp.digest(path), [251])
    with pytest.raises(cp.CheckpointError, match="initialization only"):
        cp.inspect_resume(path, {})


def test_atomic_publication_never_overwrites_and_cleans_own_temporary(tmp_path, monkeypatch):
    target = tmp_path / "step.pt"
    cp.atomic_save(target, {"value": torch.ones(1)})
    before = target.read_bytes()
    with pytest.raises(FileExistsError): cp.atomic_save(target, {"value": torch.zeros(1)})
    assert target.read_bytes() == before
    original = cp.torch.save
    def failed(*args, **kwargs): raise OSError("synthetic disk failure")
    monkeypatch.setattr(cp.torch, "save", failed)
    with pytest.raises(OSError): cp.atomic_save(tmp_path / "failed.pt", {})
    assert not (tmp_path / "failed.pt").exists() and not list(tmp_path.glob(".checkpoint-*"))
    monkeypatch.setattr(cp.torch, "save", original)
    with pytest.raises(cp.CheckpointError): cp.restricted_load(tmp_path / "missing.pt")


def test_exact_synthetic_continuation_restores_all_rng_optimizer_and_sampler(tmp_path):
    root, manifest, _ = make_cohort(tmp_path)
    index = index_for(root, manifest)
    cache = SingleCaseCache(index, (4, 4, 4))
    def fresh():
        random.seed(456); np.random.seed(456); torch.manual_seed(456)
        model = nn.Sequential(nn.Linear(4, 5), nn.BatchNorm1d(5), nn.ReLU(), nn.Dropout(.2), nn.Linear(5, 1))
        return model, torch.optim.AdamW(model.parameters(), lr=.0002, foreach=False), PatchSampler([251, 252], 456, 2)
    def step(model, optimizer, sampler):
        x, y, info = sampler.draw(cache)
        features = torch.tensor([[float(x.mean()), float(y.mean()), random.random(), np.random.random()],
                                 [float(x.std()), .2, random.random(), np.random.random()]], dtype=torch.float32)
        optimizer.zero_grad(set_to_none=True)
        loss = (model(features) - torch.rand(2, 1)).square().mean()
        loss.backward(); optimizer.step()
        return info, loss.item()
    torch.set_num_threads(1)
    a, ao, sa = fresh()
    uninterrupted = [step(a, ao, sa) for _ in range(7)]
    expected = copy.deepcopy(a.state_dict())
    b, bo, sb = fresh()
    first = [step(b, bo, sb) for _ in range(3)]
    assert first == uninterrupted[:3]
    context = {**index.contract(), "model_config": {"architecture": "SyntheticOnly"}, "seed": 456}
    state = cp.make_checkpoint(b, bo, sb, 3, context, {"kind": "synthetic", "sha256": None})
    path = tmp_path / "resume.pt"; cp.atomic_save(path, state)
    c, co, sc = fresh()
    saved = cp.inspect_resume(path, context)
    count, _ = cp.restore_checkpoint(saved, c, co, sc)
    assert count == 3
    resumed = [step(c, co, sc) for _ in range(4)]
    assert resumed == uninterrupted[3:]
    assert all(torch.equal(expected[k], v) for k, v in c.state_dict().items())
    with pytest.raises(cp.CheckpointError, match="differs"):
        cp.inspect_resume(path, {**context, "seed": 9})


def test_inconsistent_step_and_sampler_not_saved():
    model = nn.Linear(1, 1); optimizer = torch.optim.AdamW(model.parameters())
    with pytest.raises(cp.CheckpointError):
        cp.make_checkpoint(model, optimizer, PatchSampler([251]), 1, {}, {"sha256": None})
