import numpy as np
import pytest
import torch
from torch import nn

from app.services.segmentation.inference import predict_volume
from training.dataset import DataError, SingleCaseCache, normalize_patch
from training.validation import ValidationCancelled, confusion, evaluate_case, macro_average, metrics_from_counts, validate_cohort
from training.tests.test_dataset import make_cohort, index_for


def test_metrics_and_undefined_denominators():
    row = metrics_from_counts(3, 1, 2, 10)
    assert row["dice"] == pytest.approx(6/9) and row["iou"] == .5
    assert row["precision"] == .75 and row["recall"] == .6
    empty = confusion(np.zeros((2, 2, 2), bool), np.zeros((2, 2, 2), bool))
    assert empty["undefined_metrics"] == ["dice", "iou", "precision", "recall"]
    assert all(empty[k] is None for k in empty["undefined_metrics"])
    assert macro_average([row, empty])["dice"] is None
    assert macro_average([row, row])["dice"] == row["dice"]


class Pointwise(nn.Module):
    def forward(self, x): return (x - .5) * 3


def test_slabbed_validation_matches_production_blending_on_synthetic_volume(tmp_path):
    root, manifest, _ = make_cohort(tmp_path, shape=(68, 64, 64), training_ids=(251,))
    index = index_for(root, manifest, training=1)
    cache = SingleCaseCache(index)
    model = Pointwise().train()
    row = evaluate_case(model, cache, index.case(851, "Val"), threshold=.70)
    image = normalize_patch(cache.ct)
    probability = predict_volume(model, image, torch.device("cpu"), batch_size=1)
    expected = confusion(probability >= .70, cache.mask > 0)
    assert {k: row[k] for k in expected} == expected
    model.train()
    result = validate_cohort(model, cache)
    assert result["per_case"] == [row] and result["physical_metrics"] is False
    assert model.training
    with pytest.raises(DataError): evaluate_case(model, cache, index.case(251, "Training"))


def test_cancel_restores_mode_without_mutating_model_state(tmp_path):
    root, manifest, _ = make_cohort(tmp_path)
    index = index_for(root, manifest); cache = SingleCaseCache(index, (4, 4, 4))
    model = nn.BatchNorm3d(1).train()
    before = {k: v.clone() for k, v in model.state_dict().items()}
    with pytest.raises(ValidationCancelled):
        evaluate_case(model, cache, index.case(851, "Val"), stride=2, stop_requested=lambda: True)
    assert model.training and all(torch.equal(v, before[k]) for k, v in model.state_dict().items())
