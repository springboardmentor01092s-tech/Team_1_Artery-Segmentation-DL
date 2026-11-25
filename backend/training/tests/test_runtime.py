"""Synthetic device/precision/IO/orchestration tests; no CUDA GPU is needed."""
import copy
import json
from pathlib import Path
import random
import signal
from types import SimpleNamespace

import numpy as np
import pytest
import torch
from torch import nn

from training import checkpoint as cp, runtime, train
from training.dataset import DataError, SingleCaseCache
from training.losses import weighted_bce_dice
from training.sampling import PatchSampler
from training.tests.test_dataset import make_cohort, index_for


def configuration(tmp_path, root, manifest):
    cfg = json.loads(Path(train.__file__).with_name("config.example.json").read_text())
    cfg.update(dataset_root=str(root), manifest=str(manifest), output_root=str(tmp_path / "outputs"),
               expected_training_cases=2, expected_validation_cases=1, initialization_checkpoint=None,
               max_steps=2, checkpoint_every=2, validation_every=100)
    return train.validate_config(cfg)


def test_device_selection_and_explicit_cuda_failure(monkeypatch):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    assert str(runtime.select_device("auto")) == str(runtime.select_device("cpu")) == "cpu"
    with pytest.raises(ValueError, match="explicitly requested"): runtime.select_device("cuda")
    with pytest.raises(ValueError): runtime.select_device("t4")
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    assert str(runtime.select_device("auto")) == str(runtime.select_device("cuda")) == "cuda:0"
    assert str(runtime.select_device("cpu")) == "cpu"


def test_precision_configuration_and_monitoring_without_cuda(monkeypatch):
    cpu = torch.device("cpu")
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    monkeypatch.setattr(torch.cuda, "get_device_properties", lambda *a: pytest.fail("CPU monitoring must not query GPU properties"))
    monkeypatch.setattr(torch.cuda, "reset_peak_memory_stats", lambda *a: pytest.fail("No CPU peak reset"))
    assert not runtime.amp_enabled(cpu, False)
    with pytest.raises(ValueError, match="FP16"): runtime.amp_enabled(cpu, True)
    with pytest.raises(ValueError): runtime.amp_enabled(cpu, "fp16")
    assert runtime.amp_enabled(torch.device("cuda:0"), True)
    scaler = runtime.make_scaler(cpu, False)
    assert not scaler.is_enabled() and scaler.state_dict() == {}
    report = runtime.gpu_status(cpu)
    assert report["cuda_available"] is False
    assert all(report[k] is None for k in ("device_name", "total_memory_bytes", "allocated_bytes", "reserved_bytes", "peak_allocated_bytes"))
    runtime.reset_peak_memory(cpu)


def test_mocked_gpu_monitoring_and_peak_reset(monkeypatch):
    calls = []
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(torch.cuda, "get_device_properties", lambda *a: SimpleNamespace(name="Mock GPU", total_memory=16000))
    for name, value in [("memory_allocated", 100), ("memory_reserved", 200), ("max_memory_allocated", 300)]:
        monkeypatch.setattr(torch.cuda, name, lambda *a, v=value: v)
    monkeypatch.setattr(torch.cuda, "reset_peak_memory_stats", lambda device: calls.append(str(device)))
    device = torch.device("cuda:0")
    assert runtime.gpu_status(device)["peak_allocated_bytes"] == 300
    runtime.reset_peak_memory(device)
    assert calls == ["cuda:0"]
    assert runtime.gpu_status(torch.device("cpu"))["device_name"] is None


def test_cuda_rng_capture_restore_with_mocks(monkeypatch):
    calls = []
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(torch.cuda, "get_rng_state", lambda device: torch.tensor([1, 2, 3], dtype=torch.uint8))
    monkeypatch.setattr(torch.cuda, "set_rng_state", lambda state, device: calls.append((state.tolist(), device)))
    state = cp.rng_state(torch.device("cuda:0"))
    cp.restore_rng(state)
    assert calls == [([1, 2, 3], 0)]
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    with pytest.raises(cp.CheckpointError, match="CUDA RNG"): cp.restore_rng(state)


def test_half_precision_loss_reduces_in_float32():
    logits = torch.zeros((1, 1, 4, 4, 4), dtype=torch.float16, requires_grad=True)
    targets = torch.ones_like(logits)
    loss = weighted_bce_dice(logits, targets)
    assert loss.dtype == torch.float32
    loss.backward()
    assert torch.isfinite(logits.grad).all()


def test_cpu_gradscaler_unscales_before_clipping_and_roundtrips(tmp_path, monkeypatch):
    root, manifest, _ = make_cohort(tmp_path)
    index = index_for(root, manifest); cache = SingleCaseCache(index, (4, 4, 4))
    cfg = configuration(tmp_path, root, manifest)
    model = nn.Conv3d(1, 1, 1)
    optimizer = train.make_optimizer(model, cfg)
    scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=1, gamma=.9)
    sampler = PatchSampler(index.ids("Training"), patches_per_case=2)
    actual = torch.amp.GradScaler("cpu", init_scale=8., growth_interval=1, enabled=True)
    events = []
    class TrackingScaler:
        def scale(self, loss): events.append("scale"); return actual.scale(loss)
        def unscale_(self, opt): events.append("unscale"); return actual.unscale_(opt)
        def step(self, opt): events.append("step"); return actual.step(opt)
        def update(self): events.append("update"); return actual.update()
        def get_scale(self): return actual.get_scale()
    clipping = torch.nn.utils.clip_grad_norm_
    def clip(*args, **kwargs): events.append("clip"); return clipping(*args, **kwargs)
    monkeypatch.setattr(torch.nn.utils, "clip_grad_norm_", clip)
    row = train.training_step(model, optimizer, sampler, cache, cfg, scaler=TrackingScaler())
    assert events == ["scale", "unscale", "clip", "step", "update"]
    assert row["optimizer_update_performed"] and not row["amp_overflow"]
    assert all(p.dtype == torch.float32 for p in model.parameters())
    scheduler.step()
    context = {**index.contract(), "precision": "synthetic CPU scaler test"}
    saved = cp.make_checkpoint(model, optimizer, sampler, 1, context, {"sha256": None},
                               scaler=actual, scheduler=scheduler, configuration=cfg)
    path = tmp_path / "amp.pt"; cp.atomic_save(path, saved)
    expected_rng = (random.random(), float(np.random.random()), torch.rand(1))
    restored_model = nn.Conv3d(1, 1, 1)
    restored_opt = train.make_optimizer(restored_model, cfg)
    restored_scaler = torch.amp.GradScaler("cpu", enabled=True)
    restored_scheduler = torch.optim.lr_scheduler.StepLR(restored_opt, step_size=1, gamma=.9)
    restored_sampler = PatchSampler(index.ids("Training"), patches_per_case=2)
    loaded = cp.inspect_resume(path, context)
    cp.restore_checkpoint(loaded, restored_model, restored_opt, restored_sampler,
                          scaler=restored_scaler, scheduler=restored_scheduler)
    assert restored_scaler.state_dict() == actual.state_dict()
    assert restored_scheduler.state_dict() == scheduler.state_dict()
    assert loaded["configuration"] == cfg and loaded["optimizer_updates"] == 1
    assert (random.random(), float(np.random.random())) == expected_rng[:2]
    assert torch.equal(torch.rand(1), expected_rng[2])


def test_replace_publication_failure_cleans_temporary(tmp_path, monkeypatch):
    def fail_replace(source, destination):
        assert Path(source).parent == Path(destination).parent
        raise OSError("synthetic publication failure")
    monkeypatch.setattr(cp.os, "link", lambda *a: pytest.fail("Hard links must not be used"))
    monkeypatch.setattr(cp.os, "replace", fail_replace)
    with pytest.raises(OSError): cp.atomic_save(tmp_path / "failed.pt", {"tensor": torch.ones(1)})
    assert not list(tmp_path.iterdir())


def test_autocast_requests_fp16_without_allocating_a_gpu(monkeypatch):
    from contextlib import nullcontext
    calls = []
    def context(kind, **options):
        calls.append((kind, options))
        return nullcontext()
    monkeypatch.setattr(torch.amp, "autocast", context)
    with runtime.autocast_context(torch.device("cuda:0"), True): pass
    assert calls == [("cuda", {"dtype": torch.float16})]


def test_mocked_fp16_overflow_is_logged_and_update_is_skipped(tmp_path, monkeypatch):
    from contextlib import nullcontext
    root, manifest, _ = make_cohort(tmp_path)
    index = index_for(root, manifest); cfg = configuration(tmp_path, root, manifest)
    model = nn.Conv3d(1, 1, 1)
    before = {k: v.clone() for k, v in model.state_dict().items()}
    optimizer = train.make_optimizer(model, cfg)
    model.weight.register_hook(lambda gradient: torch.full_like(gradient, float("inf")))
    # Exercise GradScaler's real overflow behavior through a CPU-compatible
    # synthetic path. This does not claim CUDA kernel execution.
    monkeypatch.setattr(train, "amp_enabled", lambda *a: True)
    monkeypatch.setattr(train, "autocast_context", lambda *a: nullcontext())
    scaler = torch.amp.GradScaler("cpu", init_scale=8., enabled=True)
    row = train.training_step(model, optimizer, PatchSampler(index.ids("Training")),
                              SingleCaseCache(index, (4, 4, 4)), cfg, scaler=scaler)
    assert row["amp_overflow"] and not row["optimizer_update_performed"]
    assert row["gradient_norm_before_clip"] is None and scaler.get_scale() == 4.
    assert all(torch.equal(before[k], v) for k, v in model.state_dict().items())
    json.dumps(row, allow_nan=False)


@pytest.mark.parametrize("kind", ["signal", "keyboard"])
def test_interrupted_tiny_training_and_exact_resume(tmp_path, monkeypatch, kind):
    root, manifest, _ = make_cohort(tmp_path, shape=(64, 64, 64))
    index = index_for(root, manifest); cfg = configuration(tmp_path, root, manifest)
    monkeypatch.setattr(train, "SmallUNet3D", lambda base: nn.Conv3d(1, 1, 1))
    reference_run = train.run_training(cfg, index)
    reference = cp.restricted_load(Path(reference_run["run_directory"]) / "step-000000002.pt")
    actual_step = train.training_step
    def interrupt(*args, **kwargs):
        row = actual_step(*args, **kwargs)
        if kind == "signal": signal.raise_signal(signal.SIGINT)
        else: raise KeyboardInterrupt
        return row
    monkeypatch.setattr(train, "training_step", interrupt)
    partial = train.run_training(cfg, index)
    assert partial["stopped_by_signal"]
    assert partial["global_step"] == (1 if kind == "signal" else 0)
    snapshot = Path(partial["run_directory"]) / f"step-{partial['global_step']:09d}.pt"
    monkeypatch.setattr(train, "training_step", actual_step)
    resumed_run = train.run_training(cfg, index, snapshot)
    resumed = cp.restricted_load(Path(resumed_run["run_directory"]) / "step-000000002.pt")
    assert resumed_run["optimizer_updates"] == 2
    assert all(torch.equal(v, resumed["model_state_dict"][k]) for k, v in reference["model_state_dict"].items())
    assert reference["sampler_state"] == resumed["sampler_state"]
    assert reference["grad_scaler_state"] == resumed["grad_scaler_state"]


def test_orchestration_does_not_swallow_runtime_errors(tmp_path, monkeypatch):
    root, manifest, _ = make_cohort(tmp_path, shape=(64, 64, 64))
    cfg = configuration(tmp_path, root, manifest)
    monkeypatch.setattr(train, "SmallUNet3D", lambda base: nn.Conv3d(1, 1, 1))
    def fail(*a, **k): raise RuntimeError("synthetic failure")
    monkeypatch.setattr(train, "training_step", fail)
    before = signal.getsignal(signal.SIGINT)
    with pytest.raises(RuntimeError, match="synthetic failure"):
        train.run_training(cfg, index_for(root, manifest))
    assert signal.getsignal(signal.SIGINT) == before


def test_windows_and_posix_configs_and_local_example_defaults(tmp_path):
    original = json.loads(Path(train.__file__).with_name("config.example.json").read_text())
    local = train.validate_config(original)
    assert local["device"] == "cpu" and local["mixed_precision"] is False
    assert "device" not in original
    kaggle = copy.deepcopy(original)
    kaggle.update(dataset_root="/kaggle/input/verified-cohort", manifest="/kaggle/input/verified-manifest/split.csv",
                  output_root="/kaggle/working/new-run", cache_directory="/kaggle/temp/case-cache",
                  device="cuda", mixed_precision=True, gpu_monitoring=True)
    kaggle["initialization_checkpoint"]["path"] = "/kaggle/input/verified-weights/baseline.pt"
    assert train.validate_config(kaggle)["mixed_precision"] is True
    with pytest.raises(ValueError): train.validate_config({**kaggle, "output_root": "/kaggle/input/verified-cohort/output"})
    with pytest.raises(ValueError): train.validate_config({**kaggle, "output_root": "/kaggle/working/../input/output"})
    assert str(runtime.portable_absolute("C:/data/case")) == "C:\\data\\case"


def test_optional_single_case_disk_cache_preserves_sources(tmp_path):
    root, manifest, _ = make_cohort(tmp_path)
    index = index_for(root, manifest)
    before = {p: p.read_bytes() for p in root.rglob("*.nii.gz")}
    directory = tmp_path / "cache"; directory.mkdir(); sentinel = directory / "keep.txt"; sentinel.write_text("keep")
    cache = SingleCaseCache(index, (4, 4, 4), cache_directory=directory)
    cache.load(index.case(251, "Training"))
    assert isinstance(cache.ct, np.memmap)
    owned = [p for p in directory.iterdir() if p.is_dir()]
    assert len(owned) == 1
    cache.load(index.case(252, "Training"))
    assert not owned[0].exists() and len([p for p in directory.iterdir() if p.is_dir()]) == 1
    cache.clear()
    assert list(directory.iterdir()) == [sentinel]
    assert all(p.read_bytes() == value for p, value in before.items())
    with pytest.raises(DataError): SingleCaseCache(index, cache_directory=root / "unsafe-cache")
