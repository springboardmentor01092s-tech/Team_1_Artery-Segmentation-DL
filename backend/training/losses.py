"""The notebook's weighted mean BCE + mean per-sample soft Dice loss."""
import torch
import torch.nn.functional as F


def weighted_bce_dice(logits, targets, positive_weight=5., smooth=1e-6):
    if logits.shape != targets.shape or logits.ndim != 5 or logits.shape[1] != 1:
        raise ValueError("Expected matching single-channel NCDHW tensors.")
    if not torch.isfinite(logits).all() or not torch.isfinite(targets).all() or torch.any((targets != 0) & (targets != 1)):
        raise ValueError("Expected finite logits and binary targets.")
    # Preserve float64 analytical tests, but never reduce BCE/Dice in FP16/BF16.
    if logits.dtype in (torch.float16, torch.bfloat16):
        logits = logits.float()
    targets = targets.to(dtype=logits.dtype)
    with torch.amp.autocast(logits.device.type, enabled=False):
        weight = torch.tensor([positive_weight], dtype=logits.dtype, device=logits.device)
        bce = F.binary_cross_entropy_with_logits(logits, targets, pos_weight=weight)
        probabilities = torch.sigmoid(logits)
        axes = tuple(range(1, logits.ndim))
        intersection = (probabilities * targets).sum(dim=axes)
        denominator = probabilities.sum(dim=axes) + targets.sum(dim=axes)
        dice_loss = (1. - (2. * intersection + smooth) / (denominator + smooth)).mean()
    return bce + dice_loss
