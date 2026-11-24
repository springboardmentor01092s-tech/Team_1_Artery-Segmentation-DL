import math
import pytest
import torch

from training.losses import weighted_bce_dice


def test_exact_notebook_mean_bce_and_per_sample_dice():
    logits = torch.zeros((2, 1, 4, 4, 4), dtype=torch.float64, requires_grad=True)
    targets = torch.zeros_like(logits); targets[1] = 1
    smooth = 1e-6
    dice_empty = smooth / (32 + smooth)
    dice_full = (64 + smooth) / (96 + smooth)
    expected = 3 * math.log(2) + 1 - (dice_empty + dice_full) / 2
    loss = weighted_bce_dice(logits, targets)
    assert loss.item() == pytest.approx(expected, abs=1e-12)
    loss.backward()
    assert torch.isfinite(logits.grad).all() and torch.count_nonzero(logits.grad) > 0


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), .5, -1.])
def test_invalid_targets(bad):
    targets = torch.zeros((1, 1, 4, 4, 4)); targets[0, 0, 0, 0, 0] = bad
    with pytest.raises(ValueError): weighted_bce_dice(torch.zeros_like(targets), targets)


def test_shape_and_nonfinite_logits_rejected():
    target = torch.zeros((1, 1, 4, 4, 4))
    with pytest.raises(ValueError): weighted_bce_dice(torch.zeros((1, 2, 4, 4, 4)), target)
    with pytest.raises(ValueError): weighted_bce_dice(torch.full_like(target, float("nan")), target)
