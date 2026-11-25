"""Optional synthetic-only ML tests; no databases or real medical data."""
import json

import numpy as np
import pytest

torch = pytest.importorskip("torch", reason="optional PyTorch research runtime is not installed")

from app.services.synthetic_stenosis_ml import (
    CLASS_NAMES, DEFAULT_SHAPE, NOTICE, generate_phantom, gradcam3d, load_synthetic_model,
    make_splits, predict_synthetic, train_synthetic_model,
)


def test_synthetic_phantom_provenance_and_split_isolation():
    a = generate_phantom(4, 3, 111)
    b = generate_phantom(4, 3, 111)
    assert np.array_equal(a["volume"], b["volume"])
    assert a["provenance"] == b["provenance"]
    assert a["volume"].shape == DEFAULT_SHAPE and a["volume"].dtype == np.float32
    splits = make_splits(100, 123)
    assert not (set(splits["train"]) & set(splits["validation"]))
    assert not (set(splits["train"]) & set(splits["test"]))
    assert not (set(splits["validation"]) & set(splits["test"]))


def test_short_training_checkpoint_metrics_gradcam_and_patient_input_refusal(tmp_path):
    artifact = tmp_path / "run"
    result = train_synthetic_model(artifact, sample_count=25, epochs=1, seed=42)
    summary = result["summary"]
    assert summary["test_metrics"]["n"] == 5
    assert summary["test_metrics"]["scope"] == "synthetic_test_split_only"
    assert summary["clinical_performance_claim"] is False
    assert summary["clinical_gate_authorized"] is False
    assert summary["training_release_authorized"] is False
    assert summary["experimental_research"] is True
    assert len(summary["training_history"]) == 1
    model, loaded = load_synthetic_model(result["checkpoint"])
    assert loaded["dataset_sha256"] == summary["dataset_sha256"]
    phantom = generate_phantom(100, 2, 101)
    prediction = predict_synthetic(model, phantom)
    assert prediction["class"] in CLASS_NAMES
    assert prediction["notice"] == NOTICE
    assert prediction["clinical_gate_authorized"] is False
    instrumented = generate_phantom(101, 2, 102, include_geometry_ground_truth=True)
    assert predict_synthetic(model, instrumented)["sample_id"] == 101
    attribution = gradcam3d(model, phantom)
    assert attribution["method"] == "3d-cnn-grad-cam"
    assert np.asarray(attribution["heatmap"]).shape == DEFAULT_SHAPE
    assert np.isfinite(attribution["heatmap"]).all()
    assert attribution["clinical_validation"] is False
    assert attribution["training_release_authorized"] is False
    with pytest.raises(ValueError, match="generator provenance"):
        predict_synthetic(model, {"volume": phantom["volume"]})
    altered = dict(phantom)
    altered["volume"] = phantom["volume"].copy()
    altered["volume"][0, 0, 0] += 1
    with pytest.raises(ValueError, match="hash/shape/dtype"):
        predict_synthetic(model, altered)
    forged = dict(phantom)
    forged["volume"] = phantom["volume"].copy()
    forged["volume"][1, 1, 1] += 0.1
    forged["provenance"] = dict(phantom["provenance"])
    import hashlib
    forged["provenance"]["volume_sha256"] = hashlib.sha256(forged["volume"].tobytes(order="C")).hexdigest()
    with pytest.raises(ValueError, match="does not reproduce"):
        predict_synthetic(model, forged)
    persisted = json.loads((artifact / "training-summary.json").read_text(encoding="utf-8"))
    assert persisted["test_metrics"] == summary["test_metrics"]


def test_training_refuses_overwrite_and_invalid_size(tmp_path):
    existing = tmp_path / "already-there"
    existing.mkdir()
    with pytest.raises(FileExistsError):
        train_synthetic_model(existing, 25, 1, 1)
    with pytest.raises(ValueError):
        make_splits(24, 1)
