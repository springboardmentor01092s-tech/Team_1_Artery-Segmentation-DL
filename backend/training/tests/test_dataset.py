"""Synthetic NIfTI/index/cache tests. No real cohort voxel arrays are loaded."""
from dataclasses import replace
import csv
import json
from pathlib import Path
import weakref

import nibabel as nib
import numpy as np
import pytest

from training.dataset import DataError, SingleCaseCache, build_index, check_pair, normalize_patch


def make_cohort(tmp_path, shape=(8, 8, 8), training_ids=(251, 252), validation_ids=(851,)):
    inputs = tmp_path / "inputs"
    inputs.mkdir(parents=True)
    root = inputs / "data"
    rows = []
    for split, ids in [("Training", training_ids), ("Val", validation_ids)]:
        for cid in ids:
            start = ((cid - 1) // 200) * 200 + 1
            group = f"{start}-{start + 199}"
            folder = root / split / group
            folder.mkdir(parents=True, exist_ok=True)
            ct = np.arange(np.prod(shape), dtype=np.int16).reshape(shape) - 200
            mask = np.zeros(shape, dtype=np.float64)
            mask[1:4, 1:4, 1:4] = 1
            for kind, values, units in [("img", ct, "mm"), ("label", mask, "unknown")]:
                image = nib.Nifti1Image(values, np.diag([-.5, .5, .8, 1.]))
                image.header.set_xyzt_units(units)
                image.set_qform(None, code=0)
                image.set_sform(image.affine, code=2)
                nib.save(image, folder / f"{cid}.{kind}.nii.gz")
            rows.append({"case_id": cid, "split": split, "archive_group": group,
                         "archive_file": group + ".zip", "ct_member": group + f"\\{cid}.img.nii.gz",
                         "mask_member": group + f"\\{cid}.label.nii.gz"})
    # Deliberately unsafe member values: Testing must be excluded before using them.
    rows.append({"case_id": 1, "split": "Testing", "archive_group": "not-inspected",
                 "archive_file": "not-inspected", "ct_member": "../../DO_NOT_OPEN", "mask_member": "../../DO_NOT_OPEN"})
    manifest = inputs / "manifest.csv"
    write_manifest(manifest, rows)
    return root, manifest, rows


def write_manifest(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["case_id", "split", "archive_group", "archive_file", "ct_member", "mask_member"])
        writer.writeheader()
        writer.writerows(rows)


def index_for(root, manifest, training=2, validation=1):
    return build_index(root, manifest, expected_training=training, expected_validation=validation)


def test_index_bom_fingerprints_and_testing_exclusion(tmp_path):
    root, manifest, _ = make_cohort(tmp_path)
    index = index_for(root, manifest)
    assert index.ids("Training") == [251, 252]
    assert index.ids("Val") == [851]
    assert index.testing_excluded == 1 and 1 not in index.cases
    with pytest.raises(DataError): index.case(1, "Testing")
    with pytest.raises(DataError): index.ids("Testing")
    assert index.contract() == index_for(root, manifest).contract()
    assert len(index.manifest_fingerprint) == 64


@pytest.mark.parametrize("failure", ["duplicate", "missing", "traversal", "absolute", "wrong_group", "invalid_split"])
def test_bad_index(tmp_path, failure):
    root, manifest, rows = make_cohort(tmp_path)
    if failure == "duplicate": rows.append(dict(rows[0]))
    elif failure == "missing": (root / "Training/201-400/251.label.nii.gz").unlink()
    elif failure == "traversal": rows[0]["ct_member"] = "201-400/../../251.img.nii.gz"
    elif failure == "absolute": rows[0]["ct_member"] = "C:/private/251.img.nii.gz"
    elif failure == "wrong_group": rows[0]["archive_group"] = "401-600"
    else: rows[0]["split"] = "Train"
    write_manifest(manifest, rows)
    with pytest.raises(DataError): index_for(root, manifest)


def test_cache_streams_one_case_and_binary_targets(tmp_path, monkeypatch):
    root, manifest, _ = make_cohort(tmp_path)
    index = index_for(root, manifest)
    monkeypatch.setattr(nib.Nifti1Image, "get_fdata", lambda *a, **k: pytest.fail("No get_fdata allocation is allowed"))
    monkeypatch.setattr("training.dataset.CHUNK_BYTES", 32)
    cache = SingleCaseCache(index, (4, 4, 4))
    cache.load(index.case(251, "Training"))
    assert cache.ct.dtype == np.int16 and cache.mask.dtype == np.uint8
    assert cache.ct.nbytes + cache.mask.nbytes == 8**3 * 3
    x, y = cache.patch((0, 0, 0))
    assert x.shape == y.shape == (1, 1, 4, 4, 4)
    assert x.dtype == y.dtype == np.float32 and set(np.unique(y)) == {0, 1}
    reference = weakref.ref(cache.ct)
    cache.load(index.case(252, "Training"))
    assert reference() is None
    cache.clear()
    assert cache.ct is cache.mask is None


@pytest.mark.parametrize("value", [2., -1., .5, 1e-300, float("nan"), float("inf")])
def test_mask_validation_precedes_uint8_conversion(tmp_path, value):
    root, manifest, _ = make_cohort(tmp_path)
    path = root / "Training/201-400/251.label.nii.gz"
    image = nib.load(path)
    values = np.asanyarray(image.dataobj).copy()
    values[0, 0, 0] = value
    nib.save(nib.Nifti1Image(values, image.affine, image.header), path)
    cache = SingleCaseCache(index_for(root, manifest), (4, 4, 4))
    with pytest.raises(DataError, match="binary"):
        cache.load(cache.index.case(251, "Training"))
    assert cache.case is None


def test_cache_budget_and_source_change(tmp_path):
    root, manifest, _ = make_cohort(tmp_path)
    index = index_for(root, manifest)
    cache = SingleCaseCache(index, (4, 4, 4), max_bytes=1)
    with pytest.raises(DataError, match="budget"): cache.load(index.case(251, "Training"))
    path = index.case(251, "Training").ct
    with path.open("ab") as stream: stream.write(b"changed")
    with pytest.raises(DataError, match="changed"): check_pair(index, index.case(251, "Training"), (4, 4, 4))


def test_normalization_and_patch_boundaries(tmp_path):
    assert np.allclose(normalize_patch(np.array([-1000, -200, 0, 800, 2000], dtype=np.int16)), [0, 0, .2, 1, 1])
    raw = np.array([0, 100], dtype=np.int16)
    assert np.allclose(normalize_patch(raw, 2, -200), [0, .2])
    assert raw.tolist() == [0, 100]
    root, manifest, _ = make_cohort(tmp_path)
    cache = SingleCaseCache(index_for(root, manifest), (4, 4, 4))
    cache.load(cache.index.case(251, "Training"))
    assert cache.patch((4, 4, 4))[0].shape == (1, 1, 4, 4, 4)
    for origin in [(-1, 0, 0), (5, 0, 0)]:
        with pytest.raises(DataError): cache.patch(origin)


def test_geometry_and_unindexed_case_rejected(tmp_path):
    root, manifest, _ = make_cohort(tmp_path)
    index = index_for(root, manifest)
    assert check_pair(index, index.case(251, "Training"), (4, 4, 4))[1].units == "unknown"
    with pytest.raises(DataError): check_pair(index, replace(index.case(251, "Training"), split="Val"), (4, 4, 4))
    path = root / "Training/201-400/251.label.nii.gz"
    image = nib.load(path)
    affine = image.affine.copy(); affine[0, 3] = 5
    nib.save(nib.Nifti1Image(np.ones((8, 8, 8)), affine, image.header), path)
    fresh = index_for(root, manifest)
    with pytest.raises(DataError, match="grids"): check_pair(fresh, fresh.case(251, "Training"), (4, 4, 4))


def test_preflight_and_default_cli_never_forward_or_write(tmp_path, monkeypatch, capsys):
    from training import train
    root, manifest, _ = make_cohort(tmp_path, shape=(64, 64, 64), training_ids=(251,))
    example = Path(train.__file__).with_name("config.example.json")
    cfg = json.loads(example.read_text())
    cfg.update(dataset_root=str(root), manifest=str(manifest), output_root=str(tmp_path / "outputs"),
               expected_training_cases=1, expected_validation_cases=1, initialization_checkpoint=None)
    path = tmp_path / "config.json"; path.write_text(json.dumps(cfg))
    before = {str(p) for p in tmp_path.rglob("*")}
    monkeypatch.setattr(train.SmallUNet3D, "forward", lambda *a: pytest.fail("Preflight called forward"))
    monkeypatch.setattr(train, "run_training", lambda *a: pytest.fail("Missing --train must never train"))
    monkeypatch.setattr(train.torch.optim.AdamW, "step", lambda *a: pytest.fail("Preflight updated an optimizer"))
    assert train.main(["--config", str(path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["mode"] == "preflight_only" and result["headers_checked"] == 4
    assert result["forward_passes"] == result["optimizer_updates"] == result["testing_cases_indexed"] == 0
    assert result["unknown_mask_units"] == 2
    assert before == {str(p) for p in tmp_path.rglob("*")}
    assert not Path(cfg["output_root"]).exists()
    for field, value in [("batch_size", 2), ("num_workers", 1), ("spatial_policy", "assume_mm")]:
        with pytest.raises(ValueError): train.validate_config({**cfg, field: value})
