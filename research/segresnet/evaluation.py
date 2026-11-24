"""Native-grid binary metrics, with bounded slabs and explicit null denominators."""
import hashlib
import json
from pathlib import Path

import nibabel as nib
import numpy as np
from scipy.ndimage import affine_transform


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def metrics(counts):
    tp, fp, fn = (counts[key] for key in ("tp", "fp", "fn"))
    ratio = lambda a, b: a / b if b else None
    return {"dice": ratio(2 * tp, 2 * tp + fp + fn), "iou": ratio(tp, tp + fp + fn),
            "precision": ratio(tp, tp + fp), "recall": ratio(tp, tp + fn)}


def aggregate(rows):
    included = [row for row in rows if row.get("exclusion_reason") is None]
    macro, denominators = {}, {}
    for key in ("dice", "iou", "precision", "recall"):
        values = [row["metrics"][key] for row in included if row["metrics"][key] is not None]
        macro[key] = sum(values) / len(values) if values else None
        denominators[key] = {"defined_cases": len(values), "undefined_cases": len(included) - len(values)}
    counts = {key: sum(row["confusion_counts"][key] for row in included) for key in ("tp", "fp", "fn", "tn")}
    return {"case_count": len(rows), "included_case_count": len(included),
            "headline_aggregation": "macro_unweighted_per_case", "macro_metrics": macro,
            "macro_denominators": denominators, "pooled_micro_metrics": metrics(counts) if included else None,
            "exclusions": [{"dataset_case_id": row["dataset_case_id"], "reason": row["exclusion_reason"]}
                           for row in rows if row.get("exclusion_reason") is not None]}


def native_prediction(probability, cache_affine, native_affine, native_shape, start, stop, threshold=.5):
    """Output native IJK -> cached continuous IJK, preserving original orientation."""
    if probability.ndim != 3 or not np.isfinite(probability).all() or np.any((probability < 0) | (probability > 1)):
        raise ValueError("Expected finite foreground probabilities in [0,1]")
    if not 0 < threshold < 1 or not 0 <= start < stop <= native_shape[2]:
        raise ValueError("Invalid threshold or slab")
    transform = np.linalg.inv(cache_affine) @ native_affine
    offset = transform[:3, 3] + transform[:3, 2] * start
    sampled = affine_transform(probability, transform[:3, :3], offset=offset,
                               output_shape=(*native_shape[:2], stop - start),
                               output=np.float32, order=1, mode="constant", cval=0, prefilter=False)
    return sampled >= threshold


def evaluate_native(probability, store, case_id, output, save_prediction=False):
    record = store.info("Val", case_id)
    reference_path = store.native_reference(case_id, output)
    if sha256(reference_path) != record["reference_sha256"]:
        raise ValueError("Native reference identity differs")
    reference = nib.load(reference_path)
    shape = tuple(record["native_shape"])
    affine = np.asarray(record["native_affine"])
    if reference.shape != shape or not np.allclose(reference.affine, affine, rtol=0, atol=1e-5):
        raise ValueError("Native reference geometry differs")
    destination = Path(output) / "predictions"
    prediction = None
    scratch = None
    if save_prediction:
        destination.mkdir(exist_ok=True)
        scratch = destination / f"{case_id}.uint8.partial"
        if scratch.exists() or (destination / f"{case_id}.nii.gz").exists():
            raise FileExistsError("Refusing to overwrite a prior prediction")
        prediction = np.memmap(scratch, dtype=np.uint8, mode="w+", shape=shape)
    counts = dict(tp=0, fp=0, fn=0, tn=0)
    for start in range(0, shape[2], 16):
        stop = min(start + 16, shape[2])
        truth = np.asanyarray(reference.dataobj[:, :, start:stop])
        if not np.isfinite(truth).all() or not np.isin(truth, (0, 1)).all():
            raise ValueError("Unexpected native reference category")
        truth = truth == 1
        pred = native_prediction(probability, record["cache_affine"], affine, shape, start, stop)
        counts["tp"] += int(np.count_nonzero(pred & truth))
        counts["fp"] += int(np.count_nonzero(pred & ~truth))
        counts["fn"] += int(np.count_nonzero(~pred & truth))
        counts["tn"] += int(np.count_nonzero(~pred & ~truth))
        if prediction is not None:
            prediction[:, :, start:stop] = pred
    row = {"dataset_case_id": case_id, "ct_sha256": record["ct_sha256"],
           "reference_sha256": record["reference_sha256"], "prediction_sha256": None,
           "metrics": metrics(counts), "confusion_counts": counts, "exclusion_reason": None,
           "grid": "original_native_CT_numeric_affine", "threshold": .5,
           "spatial_assumption": record["spatial_assumption"]}
    if prediction is not None:
        prediction.flush()
        header = reference.header.copy()
        header.set_data_dtype(np.uint8)
        # Preserve original reference units (possibly unknown), never assert registration.
        image = nib.Nifti1Image(prediction, affine, header)
        image.set_sform(reference.get_sform(), int(reference.header["sform_code"]))
        qform, code = reference.get_qform(coded=True)
        if qform is not None:
            image.set_qform(qform, int(code))
        path = destination / f"{case_id}.nii.gz"
        nib.save(image, path)
        row["prediction_sha256"] = sha256(path)
        row["prediction_file"] = f"predictions/{case_id}.nii.gz"
        del image, prediction
        scratch.unlink()  # Only this invocation's disposable local scratch file.
    return row


def write_json(path, value):
    path = Path(path)
    partial = path.with_name(path.name + ".partial")
    with partial.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
    partial.replace(path)
