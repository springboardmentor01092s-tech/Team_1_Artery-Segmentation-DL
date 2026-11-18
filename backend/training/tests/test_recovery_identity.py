"""Synthetic-only portable identity and durable validation regression tests."""
import copy
import json
from pathlib import Path
import random
import shutil
import signal
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import numpy as np
import pytest
import torch
from torch import nn

from training import checkpoint as cp, train
from training.dataset import DataError, build_index
from training.identity import identity_config, sha256
from training.sampling import PatchSampler
from training.tests.test_dataset import make_cohort, index_for, write_manifest
from training.tests.test_runtime import configuration
from training.validation import ValidationCancelled


def workbook(path, assignments):
    """Small metadata-only XLSX fixture; no real source workbook is used."""
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    sheet = ET.Element("worksheet", xmlns=ns)
    data = ET.SubElement(sheet, "sheetData")
    for n, values in enumerate([("FileName", "Split-4"), *sorted(assignments.items())], 2):
        row = ET.SubElement(data, "row", r=str(n))
        for col, value in zip("AB", values):
            cell = ET.SubElement(row, "c", r=f"{col}{n}", t="inlineStr")
            ET.SubElement(ET.SubElement(cell, "is"), "t").text = str(value)
    with ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="v2-latest" sheetId="1" r:id="rId1"/></sheets></workbook>')
        archive.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        archive.writestr("xl/worksheets/sheet1.xml", ET.tostring(sheet))


def pinned_identity(tmp_path, index, *, content=True):
    path = tmp_path / "authoritative.xlsx"
    workbook(path, index.assignments)
    result = {"dataset_id": "SyntheticImageCAS", "version_id": "synthetic-v1",
              "provenance": {"workbook_path": str(path), "workbook_sha256": sha256(path),
                             "sheet": "v2-latest", "header_row": 2, "id_column": "FileName", "split_column": "Split-4"}}
    if content:
        rows = [{"case_id": c.case_id, "split": c.split,
                 "ct_member": c.ct.relative_to(index.root / c.split).as_posix(),
                 "mask_member": c.mask.relative_to(index.root / c.split).as_posix(),
                 "ct_sha256": sha256(c.ct), "mask_sha256": sha256(c.mask)} for c in index.cases.values()]
        manifest = tmp_path / "content.json"
        manifest.write_text(json.dumps({"schema_version": 1, "files": rows}))
        result.update(content_manifest=str(manifest), content_manifest_sha256=sha256(manifest), verify_content=True)
    return result


def indexed(root, manifest, identity=None):
    return build_index(root, manifest, expected_training=2, expected_validation=1, dataset_identity=identity)


def snapshot(path, context):
    model = nn.Linear(1, 1)
    state = cp.make_checkpoint(model, torch.optim.AdamW(model.parameters()), PatchSampler([251, 252]),
                               0, context, {"sha256": None})
    cp.atomic_save(path, state)
    return state


@pytest.mark.parametrize("content", [False, True])
def test_relocated_dataset_identity_and_resume(tmp_path, content):
    root, manifest, rows = make_cohort(tmp_path)
    identity = pinned_identity(tmp_path, index_for(root, manifest), content=content)
    original = indexed(root, manifest, identity)
    destination = tmp_path / "other-mount"
    shutil.copytree(root, destination)
    moved_manifest = tmp_path / "moved.csv"
    # Row order, CSV formatting and Windows/POSIX separators are not identity.
    for row in rows:
        row["ct_member"] = row["ct_member"].replace("\\", "/")
        row["mask_member"] = row["mask_member"].replace("\\", "/")
    write_manifest(moved_manifest, list(reversed(rows)))
    relocated = indexed(destination, moved_manifest, identity)
    assert original.dataset_identity == relocated.dataset_identity
    assert original.manifest_fingerprint == relocated.manifest_fingerprint
    assert original.contract()["storage"] != relocated.contract()["storage"]
    assert original.dataset_identity["level"] == ("content-verified" if content else "version-pinned")
    path = tmp_path / "snapshot.pt"
    snapshot(path, original.contract())
    assert cp.inspect_resume(path, relocated.contract())["global_step"] == 0
    if not content:
        assert original.dataset_identity["content_identity_verified"] is False


def test_structural_identity_is_not_content_or_relocation_proof(tmp_path):
    root, manifest, _ = make_cohort(tmp_path)
    original = index_for(root, manifest)
    shutil.copytree(root, tmp_path / "relocated")
    relocated = index_for(tmp_path / "relocated", manifest)
    assert original.dataset_identity == relocated.dataset_identity
    assert original.dataset_identity["level"] == "structural"
    path = tmp_path / "snapshot.pt"
    snapshot(path, original.contract())
    with pytest.raises(cp.CheckpointError, match="unverified storage differs"):
        cp.inspect_resume(path, relocated.contract())


def test_changed_content_and_manifest_tampering_are_rejected(tmp_path):
    root, manifest, _ = make_cohort(tmp_path)
    identity = pinned_identity(tmp_path, index_for(root, manifest))
    original = indexed(root, manifest, identity)
    path = original.cases[251].ct
    changed = bytearray(path.read_bytes())
    changed[-1] ^= 1
    path.write_bytes(changed)  # Same length; metadata equality cannot prove content.
    with pytest.raises(DataError, match="content SHA-256"):
        indexed(root, manifest, identity)
    content = Path(identity["content_manifest"])
    content.write_text(content.read_text() + " ")
    with pytest.raises(DataError, match="Content manifest SHA-256"):
        indexed(root, manifest, identity)


def test_workbook_and_split_changes_invalidate_identity(tmp_path):
    root, manifest, _ = make_cohort(tmp_path)
    identity = pinned_identity(tmp_path, index_for(root, manifest), content=False)
    original = indexed(root, manifest, identity)
    root2, manifest2, _ = make_cohort(tmp_path / "other", training_ids=(251, 851), validation_ids=(252,))
    with pytest.raises(DataError, match="split assignments"):
        indexed(root2, manifest2, identity)
    path = tmp_path / "snapshot.pt"
    snapshot(path, original.contract())
    with pytest.raises(cp.CheckpointError, match="differs"):
        cp.inspect_resume(path, indexed(root2, manifest2).contract())
    Path(identity["provenance"]["workbook_path"]).write_bytes(b"tampered")
    with pytest.raises(DataError, match="workbook SHA-256"):
        indexed(root, manifest, identity)


def test_pinned_canonical_manifest_and_content_mapping(tmp_path):
    root, manifest, _ = make_cohort(tmp_path)
    identity = pinned_identity(tmp_path, index_for(root, manifest))
    with pytest.raises(DataError, match="Canonical manifest"):
        indexed(root, manifest, {**identity, "expected_manifest_fingerprint": "0" * 64})
    content = Path(identity["content_manifest"])
    payload = json.loads(content.read_text())
    payload["files"][0]["split"] = "Testing"
    content.write_text(json.dumps(payload))
    with pytest.raises(DataError, match="mapping mismatch"):
        indexed(root, manifest, {**identity, "content_manifest_sha256": sha256(content)})


def test_never_inspects_testing_paths_even_with_content_verification(tmp_path, monkeypatch):
    root, manifest, _ = make_cohort(tmp_path)
    identity = pinned_identity(tmp_path, index_for(root, manifest))
    original = Path.open
    def guarded(path, *args, **kwargs):
        assert "Testing" not in path.parts and "DO_NOT_OPEN" not in str(path)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", guarded)
    assert indexed(root, manifest, identity).testing_excluded == 1


def test_identity_configuration_cross_platform_and_proof_requirements(tmp_path):
    root, manifest, _ = make_cohort(tmp_path)
    cfg = configuration(tmp_path, root, manifest)
    options = pinned_identity(tmp_path, index_for(root, manifest), content=False)
    for root_path, manifest_path, output_path, workbook_path in [
            ("C:/data/cohort", "C:/meta/split.csv", "D:/outputs/run", "C:/meta/split.xlsx"),
            ("/kaggle/input/cohort", "/kaggle/input/meta/split.csv", "/kaggle/working/run", "/kaggle/input/meta/split.xlsx")]:
        relocated = copy.deepcopy(options)
        relocated["provenance"]["workbook_path"] = workbook_path
        result = train.validate_config({**cfg, "dataset_root": root_path, "manifest": manifest_path,
                                        "output_root": output_path, "dataset_identity": relocated})
        assert result["dataset_identity"]["version_id"] == "synthetic-v1"
    with pytest.raises(DataError, match="provenance"):
        identity_config({"version_id": "unverified-version"})
    with pytest.raises(DataError, match="content manifest"):
        identity_config({**options, "verify_content": True})


def test_runtime_changes_remain_separate_from_dataset_identity(tmp_path):
    root, manifest, _ = make_cohort(tmp_path)
    context = {**index_for(root, manifest).contract(), "environment": {"torch": "synthetic", "device": "cpu"}}
    path = tmp_path / "snapshot.pt"
    saved = snapshot(path, context)
    changed = {**context, "environment": {"torch": "synthetic", "device": "cuda:0"}}
    assessment = cp.resume_assessment(saved, changed)
    assert assessment["dataset_identity_matches"] and not assessment["runtime_compatible"]
    with pytest.raises(cp.CheckpointError, match="runtime"):
        cp.inspect_resume(path, changed)


def synthetic_validation(*args, **kwargs):
    # Validation must not perturb the next training patch/optimizer RNG stream.
    random.random(); np.random.random(); torch.rand(3)
    return {"cases": [], "macro": {"dice": .25}, "synthetic": True}


@pytest.mark.parametrize("interruption", ["before", "during", "during_keyboard", "during_error", "after", "published"])
def test_pending_validation_recovery_and_exact_continuation(tmp_path, monkeypatch, interruption):
    root, manifest, _ = make_cohort(tmp_path, shape=(64, 64, 64))
    index = index_for(root, manifest)
    cfg = {**configuration(tmp_path, root, manifest), "max_steps": 3, "validation_every": 2}
    monkeypatch.setattr(train, "SmallUNet3D", lambda base: nn.Conv3d(1, 1, 1))
    monkeypatch.setattr(train, "validate_cohort", synthetic_validation)
    baseline = train.run_training(cfg, index)
    expected = cp.restricted_load(baseline["latest_checkpoint"])
    actual_step, actual_save = train.training_step, train.atomic_save
    events = []
    def interrupt_step(*args, **kwargs):
        events.append("training")
        row = actual_step(*args, **kwargs)
        if interruption == "before" and len(events) == 2:
            signal.raise_signal(signal.SIGINT)
        return row
    def interrupted_validation(*args, **kwargs):
        events.append("validation")
        result = synthetic_validation()
        if interruption == "during":
            raise ValidationCancelled()
        if interruption == "during_keyboard":
            raise KeyboardInterrupt()
        if interruption == "during_error":
            raise RuntimeError("synthetic validation failure")
        if interruption == "after":
            signal.raise_signal(signal.SIGINT)
        return result
    def interrupted_save(path, value):
        actual_save(path, value)
        if interruption == "published" and value["phase"] == "validation_completed":
            raise RuntimeError("synthetic crash after atomic completion publication")
    monkeypatch.setattr(train, "training_step", interrupt_step)
    monkeypatch.setattr(train, "validate_cohort", interrupted_validation)
    monkeypatch.setattr(train, "atomic_save", interrupted_save)
    if interruption in ("published", "during_error"):
        with pytest.raises(RuntimeError, match="synthetic"):
            train.run_training(cfg, index)
        paths = set(Path(cfg["output_root"]).glob("*/step-000000002.pt"))
        pending = next(p for p in paths if p.parent != Path(baseline["run_directory"]))
    else:
        partial = train.run_training(cfg, index)
        assert partial["global_step"] == 2
        pending = Path(partial["run_directory"]) / "step-000000002.pt"
    raw = cp.restricted_load(pending)
    assert raw["validation_state"]["pending"] and raw["phase"] == "validation_pending"
    inspected = cp.inspect_resume(pending, train.context_for(train.validate_config(cfg), index))
    assert inspected["validation_state"]["completed"] == (interruption in ("after", "published"))
    events.clear()
    monkeypatch.setattr(train, "atomic_save", actual_save)
    def resumed_step(*args, **kwargs):
        events.append("training")
        return actual_step(*args, **kwargs)
    def resumed_validation(*args, **kwargs):
        events.append("validation")
        return synthetic_validation()
    monkeypatch.setattr(train, "training_step", resumed_step)
    monkeypatch.setattr(train, "validate_cohort", resumed_validation)
    resumed = train.run_training(cfg, index, pending)
    assert events == (["training"] if interruption in ("after", "published") else ["validation", "training"])
    final = cp.restricted_load(resumed["latest_checkpoint"])
    assert final["validation_state"] == expected["validation_state"]
    assert final["sampler_state"] == expected["sampler_state"]
    assert final["optimizer_updates"] == expected["optimizer_updates"]
    assert all(torch.equal(v, final["model_state_dict"][k]) for k, v in expected["model_state_dict"].items())
    assert torch.equal(final["rng_states"]["torch_cpu"], expected["rng_states"]["torch_cpu"])
    for key in ("python", "numpy"):
        assert final["rng_states"][key] == expected["rng_states"][key]
    for key, state in expected["optimizer_state_dict"]["state"].items():
        assert all(torch.equal(value, final["optimizer_state_dict"]["state"][key][name]) for name, value in state.items())


def test_pending_validation_at_maximum_and_completed_resume_no_duplicate(tmp_path, monkeypatch):
    root, manifest, _ = make_cohort(tmp_path, shape=(64, 64, 64))
    index = index_for(root, manifest)
    cfg = {**configuration(tmp_path, root, manifest), "validation_every": 2}
    monkeypatch.setattr(train, "SmallUNet3D", lambda base: nn.Conv3d(1, 1, 1))
    actual = train.training_step
    def stop_at_boundary(*args, **kwargs):
        row = actual(*args, **kwargs)
        if args[2].draws == 2:
            signal.raise_signal(signal.SIGINT)
        return row
    monkeypatch.setattr(train, "training_step", stop_at_boundary)
    partial = train.run_training(cfg, index)
    calls = []
    def validate(*args, **kwargs):
        calls.append("validation")
        return synthetic_validation()
    monkeypatch.setattr(train, "training_step", lambda *a, **k: pytest.fail("No update allowed at max step"))
    monkeypatch.setattr(train, "validate_cohort", validate)
    done = train.run_training(cfg, index, partial["latest_checkpoint"])
    assert calls == ["validation"] and done["validation_state"]["completed"]
    train.run_training(cfg, index, done["latest_checkpoint"])
    assert calls == ["validation"]


def test_validation_state_rejects_skipped_or_advanced_pending_boundaries():
    with pytest.raises(cp.CheckpointError, match="skipped"):
        cp.validation_phase(cp.initial_validation_state(), 2, 2)
    pending = {**cp.initial_validation_state(), "pending": True, "validation_step": 2}
    with pytest.raises(cp.CheckpointError, match="advanced"):
        cp.validation_phase(pending, 3, 2)


@pytest.mark.parametrize("level", ["structural", "version-pinned", "content-verified"])
def test_preflight_reports_identity_and_recovery_without_voxel_decoding(tmp_path, monkeypatch, level):
    root, manifest, _ = make_cohort(tmp_path, shape=(64, 64, 64))
    cfg = configuration(tmp_path, root, manifest)
    if level != "structural":
        cfg["dataset_identity"] = pinned_identity(tmp_path / "inputs", index_for(root, manifest), content=level == "content-verified")
    import training.dataset as dataset
    monkeypatch.setattr(dataset, "_chunks", lambda *a: pytest.fail("No voxel arrays in preflight"))
    before = set(tmp_path.rglob("*"))
    _, report = train.preflight(cfg)
    assert report["dataset_identity_level"] == level
    assert (report["manifest_provenance"] is None) == (level == "structural")
    assert report["validation_recovery"] == cp.initial_validation_state()
    assert report["runtime_compatibility"]["exact_resume_supported"] is None
    assert report["initialization"]["kind"] == "fresh_seeded_initialization"
    assert report["forward_passes"] == 0 and set(tmp_path.rglob("*")) == before


@pytest.mark.parametrize("completed", [False, True])
def test_preflight_reports_exact_resume_pending_and_completed(tmp_path, monkeypatch, completed):
    root, manifest, _ = make_cohort(tmp_path, shape=(64, 64, 64))
    cfg = train.validate_config({**configuration(tmp_path, root, manifest), "validation_every": 2})
    index = index_for(root, manifest)
    model = train.SmallUNet3D(base=8)  # State loading only; no model forward.
    sampler = PatchSampler(index.ids("Training"), cfg["seed"], cfg["sampling"]["patches_per_case"])
    from training.dataset import SingleCaseCache
    cache = SingleCaseCache(index)
    sampler.draw(cache); sampler.draw(cache)  # Synthetic NIfTI only.
    cache.clear()
    recovery = {"pending": not completed, "completed": completed, "validation_step": 2,
                "last_completed_step": 2 if completed else None,
                "last_completed_result": {"synthetic": True} if completed else None}
    state = cp.make_checkpoint(model, train.make_optimizer(model, cfg), sampler, 2,
                               train.context_for(cfg, index), {"sha256": None}, validation_state=recovery,
                               scaler=train.make_scaler(torch.device("cpu"), False), configuration=cfg)
    path = tmp_path / "resume.pt"
    cp.atomic_save(path, state)
    monkeypatch.setattr(type(model), "forward", lambda *a: pytest.fail("No inference allowed in preflight"))
    _, report = train.preflight(cfg, path)
    assert report["validation_recovery"] == recovery
    assert report["runtime_compatibility"]["exact_resume_supported"] is True
    assert report["initialization"]["kind"] == "new_experiment_resume"


def test_unbound_completed_sibling_rejected(tmp_path):
    root, manifest, _ = make_cohort(tmp_path)
    index = index_for(root, manifest)
    model = nn.Linear(1, 1)
    sampler = PatchSampler(index.ids("Training"))
    sampler.draws = 2
    sampler.patch_cursor = 2
    optimizer = torch.optim.AdamW(model.parameters())
    pending = {**cp.initial_validation_state(), "pending": True, "validation_step": 2}
    state = cp.make_checkpoint(model, optimizer, sampler, 2, index.contract(), {"sha256": None}, validation_state=pending)
    path = tmp_path / "step-000000002.pt"
    cp.atomic_save(path, state)
    done = {"pending": False, "completed": True, "validation_step": 2,
            "last_completed_step": 2, "last_completed_result": {"synthetic": True}}
    state = cp.make_checkpoint(model, optimizer, sampler, 2, index.contract(), {"sha256": None}, validation_state=done)
    state["validation_parent_sha256"] = "0" * 64
    cp.atomic_save(tmp_path / "step-000000002-validation-completed.pt", state)
    with pytest.raises(cp.CheckpointError, match="not bound"):
        cp.inspect_resume(path, index.contract())


def test_second_pending_validation_retains_last_completed_result(tmp_path, monkeypatch):
    root, manifest, _ = make_cohort(tmp_path, shape=(64, 64, 64))
    index = index_for(root, manifest)
    cfg = {**configuration(tmp_path, root, manifest), "max_steps": 5, "validation_every": 2}
    monkeypatch.setattr(train, "SmallUNet3D", lambda base: nn.Conv3d(1, 1, 1))
    actual = train.training_step
    def stop_at_four(*args, **kwargs):
        row = actual(*args, **kwargs)
        if args[2].draws == 4:
            signal.raise_signal(signal.SIGINT)
        return row
    monkeypatch.setattr(train, "training_step", stop_at_four)
    monkeypatch.setattr(train, "validate_cohort", synthetic_validation)
    result = train.run_training(cfg, index)
    saved = cp.inspect_resume(result["latest_checkpoint"], train.context_for(train.validate_config(cfg), index))
    assert saved["validation_state"] == {"pending": True, "completed": False, "validation_step": 4,
                                         "last_completed_step": 2, "last_completed_result": synthetic_validation()}
    monkeypatch.setattr(train, "training_step", actual)
    final = train.run_training(cfg, index, result["latest_checkpoint"])
    assert final["global_step"] == 5
    assert final["validation_state"]["last_completed_step"] == 4
