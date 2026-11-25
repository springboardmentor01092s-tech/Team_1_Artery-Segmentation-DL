"""Deterministic voxelwise validation. No physical metrics or Testing access."""
from collections import Counter
import math

import numpy as np
import torch

from app.services.segmentation.inference import sliding_starts
from .dataset import DataError, normalize_patch
from .runtime import autocast_context


class ValidationCancelled(Exception):
    pass


def metrics_from_counts(tp, fp, fn, tn):
    if any(not isinstance(v, int) or v < 0 for v in (tp, fp, fn, tn)):
        raise ValueError("Confusion counts must be nonnegative integers.")
    fractions = {"dice": (2 * tp, 2 * tp + fp + fn), "iou": (tp, tp + fp + fn),
                 "precision": (tp, tp + fp), "recall": (tp, tp + fn)}
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            **{name: num / den if den else None for name, (num, den) in fractions.items()},
            "undefined_metrics": [name for name, (_, den) in fractions.items() if not den]}


def confusion(prediction, reference):
    if prediction.shape != reference.shape:
        raise ValueError("Prediction/reference shapes differ.")
    p, y = np.asarray(prediction, dtype=bool), np.asarray(reference, dtype=bool)
    tp = int(np.count_nonzero(p & y))
    return metrics_from_counts(tp, int(np.count_nonzero(p & ~y)), int(np.count_nonzero(~p & y)), int(np.count_nonzero(~p & ~y)))


def macro_average(rows):
    names = ("dice", "iou", "precision", "recall")
    return {name: sum(row[name] for row in rows) / len(rows)
            if rows and all(row[name] is not None for row in rows) else None for name in names}


def evaluate_case(model, cache, case, *, threshold=.70, stride=32, stop_requested=lambda: False,
                  device=None, mixed_precision=False):
    """Use production boundary starts, sigmoid and uniform blending, slab by slab.

    Accumulate only one patch-depth slab (not a whole float32 volume). The
    accumulation order per voxel matches ascending i,j,k patch traversal.
    """
    if case.split != "Val" or not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise DataError("Validation requires a Val case and a finite threshold.")
    patch = cache.patch_size
    if len(set(patch)) != 1 or not 1 <= stride <= min(patch):
        raise DataError("Invalid validation windows.")
    if math.prod(math.ceil(p / stride) for p in patch) > np.iinfo(np.uint16).max:
        raise DataError("Validation overlap exceeds the uint16 coverage limit.")
    device = torch.device(device) if device is not None else next(model.parameters(), torch.empty(0)).device
    if mixed_precision and device.type != "cuda":
        raise DataError("Validation FP16 requires CUDA.")
    cache.load(case)
    shape = cache.ct.shape
    starts = [sliding_starts(d, p, stride) for d, p in zip(shape, patch)]
    was_training = model.training
    counts = Counter(tp=0, fp=0, fn=0, tn=0)
    model.eval()
    try:
        with torch.inference_mode():
            # Slabs follow array axis 0. Patches crossing a slab edge are repeated;
            # eval-mode outputs are identical and no full probability array is kept.
            for lower in range(0, shape[0], patch[0]):
                upper = min(lower + patch[0], shape[0])
                sums = np.zeros((upper - lower, shape[1], shape[2]), dtype=np.float32)
                coverage = np.zeros(sums.shape, dtype=np.uint16)
                for i in starts[0]:
                    a, b = max(i, lower), min(i + patch[0], upper)
                    if a >= b:
                        continue
                    for j in starts[1]:
                        for k in starts[2]:
                            if stop_requested():
                                raise ValidationCancelled
                            raw = cache.ct[i:i+patch[0], j:j+patch[1], k:k+patch[2]]
                            x = normalize_patch(raw, cache.ct_header.slope, cache.ct_header.intercept)
                            with autocast_context(device, mixed_precision):
                                logits = model(torch.from_numpy(x[None, None]).to(device))
                            if tuple(logits.shape) != (1, 1, *patch) or not torch.isfinite(logits).all():
                                raise DataError("Invalid validation logits.")
                            probabilities = torch.sigmoid(logits.float())[0, 0].cpu().numpy()
                            region = (slice(a-lower, b-lower), slice(j, j+patch[1]), slice(k, k+patch[2]))
                            sums[region] += probabilities[a-i:b-i]
                            coverage[region] += 1
                if np.any(coverage == 0):
                    raise DataError("Validation did not cover every voxel.")
                sums /= coverage
                row = confusion(sums >= threshold, cache.mask[lower:upper] > 0)
                counts.update({key: row[key] for key in counts})
    finally:
        model.train(was_training)
    return {"case_id": case.case_id, **metrics_from_counts(**dict(counts))}


def validate_cohort(model, cache, *, threshold=.70, stride=32, stop_requested=lambda: False,
                    device=None, mixed_precision=False):
    rows = []
    for cid in cache.index.ids("Val"):
        rows.append(evaluate_case(model, cache, cache.index.case(cid, "Val"), threshold=threshold,
                                  stride=stride, stop_requested=stop_requested,
                                  device=device, mixed_precision=mixed_precision))
    return {"per_case": rows, "macro_mean_per_case": macro_average(rows), "threshold": threshold,
            "physical_metrics": False, "anatomical_registration": "not independently verified"}
