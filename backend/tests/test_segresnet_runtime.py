"""Synthetic recipe, coordinate and dispatch regressions; no DB/model downloads."""
from pathlib import Path
from uuid import uuid4
import hashlib

import nibabel as nib
import numpy as np
import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("monai")
from app.services.segmentation import segresnet as runtime
from app.services.segmentation.inference import InferenceError


@pytest.fixture
def checkpoint(tmp_path):
    model = runtime.SegResNet(**runtime.MODEL)
    path = tmp_path / "synthetic.pt"
    torch.save({"model": model.state_dict(), "optimizer_steps": 7,
                "provenance": {"schema_version": "segresnet-training/1.0", "model": "MONAI SegResNet",
                               "model_config": {**runtime.MODEL, "blocks_down": (1, 2, 2, 4)},
                               "threshold": .5, "patch": [96, 96, 96], "monai": "1.6.1",
                               "training_run_id": str(uuid4())}}, path)
    return path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source(array, affine=None):
    image = nib.Nifti1Image(array, np.eye(4) if affine is None else affine)
    image.header.set_xyzt_units("mm")
    return image


def test_checkpoint_explicit_identity_and_strict_state(checkpoint):
    model, identity = runtime.load_model(checkpoint, torch.device("cpu"), digest(checkpoint))
    assert not model.training and identity["optimizer_steps"] == 7
    with pytest.raises(InferenceError, match="SHA-256"):
        runtime.load_model(checkpoint, torch.device("cpu"), None)
    with pytest.raises(InferenceError, match="could not be verified"):
        runtime.load_model(checkpoint, torch.device("cpu"), "0" * 64)


@pytest.mark.parametrize("mutation", ["threshold", "patch", "model_config", "monai", "optimizer_steps", "weights", "nonfinite"])
def test_incompatible_recipe_rejected_even_with_matching_hash(checkpoint, mutation):
    obj = torch.load(checkpoint, weights_only=True)
    if mutation == "weights":
        obj["model"].pop(next(iter(obj["model"])))
    elif mutation == "nonfinite":
        obj["model"][next(iter(obj["model"]))].fill_(float("nan"))
    elif mutation == "optimizer_steps":
        obj[mutation] = 0
    else:
        obj["provenance"][mutation] = {"threshold": .7, "patch": [64] * 3,
                                        "model_config": {}, "monai": "unknown"}[mutation]
    torch.save(obj, checkpoint)
    with pytest.raises(InferenceError, match="could not be verified"):
        runtime.load_model(checkpoint, torch.device("cpu"), digest(checkpoint))


def test_unrecognized_pickle_fails_closed(tmp_path):
    path = tmp_path / "invalid.pt"
    torch.save({"unexpected": Path("not-a-tensor")}, path)
    with pytest.raises(InferenceError, match="could not be verified"):
        runtime.load_model(path, torch.device("cpu"), digest(path))


def test_checkpoint_changed_while_loading_is_rejected(checkpoint, monkeypatch):
    expected = digest(checkpoint)
    original = runtime.torch.load
    def changed(*args, **kwargs):
        value = original(*args, **kwargs)
        with checkpoint.open("ab") as stream:
            stream.write(b"synthetic mutation")
        return value
    monkeypatch.setattr(runtime.torch, "load", changed)
    with pytest.raises(InferenceError, match="could not be verified"):
        runtime.load_model(checkpoint, torch.device("cpu"), expected)


def test_incompatible_runtime_version_rejected_before_checkpoint_read(monkeypatch):
    monkeypatch.setattr(runtime.monai, "__version__", "unsupported")
    with pytest.raises(InferenceError, match="MONAI 1.6.1"):
        runtime.load_model("does-not-exist", torch.device("cpu"), "a" * 64)


@pytest.mark.parametrize("spacing", [(1, 1, 1), (.7, .9, 1.3)])
def test_preprocessing_matches_frozen_cache_with_oblique_axes(spacing):
    theta = .37
    rotation = np.array([[np.cos(theta), -np.sin(theta), 0], [np.sin(theta), np.cos(theta), 0], [0, 0, 1]])
    affine = np.eye(4)
    affine[:3, :3] = rotation @ np.diag(spacing)
    affine[:3, 3] = [12, -25, 7]
    raw = np.arange(7 * 9 * 11, dtype=np.float32).reshape(7, 9, 11) * 3 - 600
    image = source(raw, affine)
    result, grid = runtime.prepare_input(image, raw)
    # Independent physical-coordinate interpolation using map_coordinates,
    # rather than round-tripping the implementation's affine_transform.
    from scipy.ndimage import map_coordinates
    coordinates = np.indices(result.shape).reshape(3, -1)
    physical = grid[:3, :3] @ coordinates + grid[:3, 3:4]
    ijk = np.linalg.solve(image.affine[:3, :3], physical - image.affine[:3, 3:4])
    expected = map_coordinates(raw, ijk, order=1, mode="constant", cval=-200, prefilter=False)
    expected = ((np.clip(expected, -200, 800) + 200) / 1000).astype(np.float16).astype(np.float32)
    # At mathematically exact borders, roundoff in independently inverted
    # coordinates can differ in exterior classification; compare interior.
    interior = ((ijk > 1e-8) & (ijk < np.array(raw.shape)[:, None] - 1 - 1e-8)).all(axis=0)
    np.testing.assert_array_equal(result.ravel()[interior], expected[interior])
    np.testing.assert_allclose(np.linalg.norm(grid[:3, :3], axis=0), 1)
    np.testing.assert_array_equal(grid[:3, 3], image.affine[:3, 3])
    assert raw.flat[0] == -600


@pytest.mark.parametrize("kind", ["unknown_units", "shear", "resource"])
def test_geometry_and_resource_fail_before_resampling(monkeypatch, kind):
    image = source(np.zeros((3, 4, 5), dtype=np.float32))
    if kind == "unknown_units":
        image.header.set_xyzt_units("unknown")
    elif kind == "shear":
        affine = image.affine.copy()
        affine[0, 1] = .3
        image.set_sform(affine)
    else:
        monkeypatch.setattr(runtime, "MAX_CACHE_VOXELS", 2)
    monkeypatch.setattr(runtime, "affine_transform", lambda *a, **k: pytest.fail("Resampling must not start"))
    with pytest.raises(InferenceError):
        runtime.prepare_input(image, np.zeros(image.shape, dtype=np.float32))


def test_native_slab_mapping_independent_linear_field():
    cache = np.eye(4)
    cache[:3, 3] = [10, -20, 5]
    native = cache.copy()
    native[:3, :3] = np.diag([.5, .75, .4])
    values = np.indices((12, 13, 15), dtype=np.float32)
    probability = .1 + .01 * values[0] + .02 * values[1] + .005 * values[2]
    result = runtime.restore_native(probability, cache, native, (16, 15, 32))
    ijk = np.indices(result.shape)
    expected = .1 + .005 * ijk[0] + .015 * ijk[1] + .002 * ijk[2]
    np.testing.assert_allclose(result, expected, atol=1e-7, rtol=0)


@pytest.mark.parametrize("threshold", [0, .7, 1, float("nan"), True])
def test_no_threshold_retuning_before_loading(tmp_path, threshold):
    with pytest.raises(InferenceError, match="threshold 0.5"):
        runtime.run_inference("unused", "unused", tmp_path / "no-output", threshold)
    assert not (tmp_path / "no-output").exists()


def test_synthetic_complete_runtime_keeps_native_geometry(tmp_path, monkeypatch):
    raw = np.zeros((5, 7, 19), dtype=np.int16)
    image = source(raw, np.diag([.8, .9, 1.2, 1]))
    path = tmp_path / "synthetic.nii.gz"
    nib.save(image, path)
    monkeypatch.setattr(runtime, "load_model", lambda *a: (None, {"training_run_id": str(uuid4()), "optimizer_steps": 7}))
    monkeypatch.setattr(runtime, "predict", lambda model, data, *a: np.full(data.shape, .6, dtype=np.float32))
    result = runtime.run_inference(path, "synthetic-only", tmp_path / "output", expected_checkpoint_sha256="a" * 64)
    mask = nib.load(tmp_path / "output/prediction_mask.nii.gz")
    assert mask.shape == raw.shape and set(np.unique(mask.dataobj)) <= {0, 1}
    np.testing.assert_array_equal(mask.affine, nib.load(path).affine)
    assert result["clinical_validation"] is False and result["threshold"] == .5
    assert result["recipe"] == "segresnet-1mm-v1"
    assert "severity" not in result


def test_source_change_during_prediction_never_publishes_output(tmp_path, monkeypatch):
    path = tmp_path / "synthetic.nii.gz"
    nib.save(source(np.zeros((3, 4, 5), dtype=np.int16)), path)
    monkeypatch.setattr(runtime, "load_model", lambda *a: (None, {"training_run_id": str(uuid4()), "optimizer_steps": 7}))
    def mutate(model, data, *args):
        with path.open("ab") as stream:
            stream.write(b"changed source")
        return np.zeros(data.shape, dtype=np.float32)
    monkeypatch.setattr(runtime, "predict", mutate)
    with pytest.raises(InferenceError, match="changed during inference") as error:
        runtime.run_inference(path, "synthetic-only", tmp_path / "output", expected_checkpoint_sha256="a" * 64)
    assert error.value.status_code == 409 and not (tmp_path / "output").exists()
