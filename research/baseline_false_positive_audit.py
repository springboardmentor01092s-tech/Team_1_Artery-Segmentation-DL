"""Read saved case-851 outputs only. No model imports, inference or training.

Pure array diagnostics are reusable; the CLI deliberately allowlists the supplied
validation case and writes only to a new directory outside this repository.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import sys

import nibabel as nib
import numpy as np


CHECKPOINT_SHA256 = "e208fa586bb9bb50dc77b913caa0355a547bad529f9f0d61df17880b2efc5254"
THRESHOLDS = (0.50, 0.60, 0.70, 0.80)
ALIGNMENT_NOTE = (
    "Reference spatial units are unknown while CT units are mm. Explicit voxelwise "
    "correspondence is assumed only after matching dimensions, selected affine and "
    "spacing. Matching headers do not independently establish anatomical registration "
    "or annotation completeness. No resampling or header editing is performed."
)


class AuditError(ValueError):
    """An input is unverifiable; do not publish diagnostic measurements."""


def require(condition, message):
    if not condition:
        raise AuditError(message)


def sha256(path):
    digest = hashlib.sha256()
    before = path.stat()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    after = path.stat()
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    require(all(getattr(before, field) == getattr(after, field) for field in fields),
            f"Input changed while hashing: {path.name}")
    return digest.hexdigest()


def describe_geometry(image):
    return {
        "shape": list(image.shape), "affine": image.affine.tolist(),
        "spacing": [float(value) for value in image.header.get_zooms()],
        "axis_codes": list(nib.aff2axcodes(image.affine)),
        "units": list(image.header.get_xyzt_units()), "dtype": str(image.get_data_dtype()),
        "qform_code": int(image.header["qform_code"]), "sform_code": int(image.header["sform_code"]),
        "qform": image.get_qform().tolist(), "sform": image.get_sform().tolist(),
    }


def validate_geometry(images, metadata, allow_reference_unknown_units=False):
    ct = images["ct"]
    require(len(ct.shape) == 3 and all(value > 0 for value in ct.shape), "CT must be three-dimensional")
    require(ct.header.get_xyzt_units()[0] == "mm", "Expected CT spatial units mm")
    for name, image in images.items():
        require(image.shape == ct.shape, f"{name}: dimensions differ from CT")
        require(np.isfinite(image.affine).all() and abs(np.linalg.det(image.affine[:3, :3])) > 0,
                f"{name}: invalid affine")
        require(np.allclose(image.affine, ct.affine, rtol=0, atol=1e-6), f"{name}: affine differs from CT")
        require(np.allclose(image.header.get_zooms(), ct.header.get_zooms(), rtol=0, atol=1e-6),
                f"{name}: spacing differs from CT")
        require(int(image.header["qform_code"]) > 0 or int(image.header["sform_code"]) > 0,
                f"{name}: no coded spatial transform")
        units = image.header.get_xyzt_units()[0]
        permitted = name == "reference" and units == "unknown" and allow_reference_unknown_units
        require(units == "mm" or permitted, f"{name}: spatial units mismatch; explicit unknown-reference opt-in required")
    require(list(ct.shape) == metadata.get("shape"), "Run metadata dimensions mismatch")
    recorded_affine = np.asarray(metadata.get("affine"))
    require(recorded_affine.shape == (4, 4) and np.allclose(recorded_affine, ct.affine, rtol=0, atol=1e-6),
            "Run metadata affine mismatch")
    require(metadata.get("xyzt_units") == int(ct.header["xyzt_units"]), "Run metadata units mismatch")
    return {name: describe_geometry(image) for name, image in images.items()}


def validate_arrays(probability, saved_mask, reference_values, ct):
    require(probability.shape == saved_mask.shape == reference_values.shape == ct.shape,
            "Array dimensions mismatch")
    require(np.isfinite(probability).all() and np.all((probability >= 0) & (probability <= 1)),
            "Probabilities must be finite and in [0, 1]")
    require(np.isfinite(reference_values).all() and np.isfinite(ct).all(), "Non-finite CT or reference")
    require(np.all((saved_mask == 0) | (saved_mask == 1)), "Saved prediction must be binary")
    require(np.array_equal(saved_mask > 0, probability >= 0.70), "Saved prediction differs from probability >= 0.70")


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def confusion(prediction, reference):
    require(prediction.shape == reference.shape, "Confusion-array dimensions mismatch")
    prediction, reference = prediction > 0, reference > 0
    tp = int(np.count_nonzero(prediction & reference))
    predicted, target = int(np.count_nonzero(prediction)), int(np.count_nonzero(reference))
    fp, fn = predicted - tp, target - tp
    result = {
        "tp": tp, "fp": fp, "fn": fn, "tn": int(reference.size) - tp - fp - fn,
        "predicted_foreground": predicted, "reference_foreground": target,
        "dice": ratio(2 * tp, predicted + target), "iou": ratio(tp, tp + fp + fn),
        "precision": ratio(tp, predicted), "recall": ratio(tp, target),
    }
    result["undefined_metrics"] = [name for name in ("dice", "iou", "precision", "recall") if result[name] is None]
    return result


def distribution(values):
    values = np.asarray(values)
    if not values.size:
        return {"count": 0, "mean": None, "quantiles": None}
    quantiles = (0, .25, .50, .75, .90, .95, .99, 1)
    return {"count": int(values.size), "mean": float(values.mean(dtype=np.float64)),
            "quantiles": dict(zip(map(str, quantiles), np.quantile(values, quantiles).tolist()))}


def connected_components(prediction, reference):
    """Sparse 6-connectivity: face-sharing +/-1 on one array axis, no wrapping.

    No full-volume integer label array or new image is written. Stable IDs follow
    the first foreground voxel in C-order. Physical distances are not inferred.
    """
    require(prediction.ndim == 3 and prediction.shape == reference.shape, "Components require matching 3D arrays")
    indices = np.flatnonzero(prediction)
    remaining = set(indices.tolist())
    target = (reference > 0).ravel()
    nx, ny, nz = prediction.shape
    plane = ny * nz
    rows = []
    for seed in indices:
        seed = int(seed)
        if seed not in remaining:
            continue
        remaining.remove(seed)
        pending, size, tp = [seed], 0, 0
        while pending:
            index = pending.pop()
            size += 1
            tp += int(target[index])
            i, remainder = divmod(index, plane)
            j, k = divmod(remainder, nz)
            neighbors = []
            if i: neighbors.append(index - plane)
            if i + 1 < nx: neighbors.append(index + plane)
            if j: neighbors.append(index - nz)
            if j + 1 < ny: neighbors.append(index + nz)
            if k: neighbors.append(index - 1)
            if k + 1 < nz: neighbors.append(index + 1)
            for neighbor in neighbors:
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    pending.append(neighbor)
        fp = size - tp
        rows.append({"component_id": len(rows) + 1, "first_flat_index_c_order": seed,
                     "voxels": size, "tp": tp, "fp": fp,
                     "kind": "zero_reference_overlap" if tp == 0 else "mixed_tp_fp" if fp else "all_tp"})
    return rows


def component_summary(rows):
    total = sum(row["voxels"] for row in rows)
    fp = sum(row["fp"] for row in rows)
    groups = {}
    for kind in ("zero_reference_overlap", "mixed_tp_fp", "all_tp"):
        selected = [row for row in rows if row["kind"] == kind]
        groups[kind] = {"components": len(selected),
                        **{field: sum(row[field] for row in selected) for field in ("voxels", "tp", "fp")}}
        groups[kind]["fraction_of_all_fp"] = ratio(groups[kind]["fp"], fp)
    sizes = np.array([row["voxels"] for row in rows], dtype=np.int64)
    bins = []
    for lower, upper in ((1, 1), (2, 9), (10, 99), (100, 999), (1000, 9999), (10000, None)):
        selected = [row for row in rows if row["voxels"] >= lower and (upper is None or row["voxels"] <= upper)]
        bins.append({"min_voxels": lower, "max_voxels": upper, "components": len(selected),
                     **{field: sum(row[field] for row in selected) for field in ("voxels", "tp", "fp")}})
    largest = max(rows, key=lambda row: row["voxels"]) if rows else None
    return {"connectivity": "6: face-sharing neighbors only, no diagonals", "count": len(rows),
            "size_distribution": distribution(sizes), "size_bins": bins, "groups": groups,
            "largest": dict(largest, fraction_of_foreground=ratio(largest["voxels"], total)) if largest else None}


def probability_histogram(probability, reference, bins=50):
    edges = np.linspace(0, 1, bins + 1)
    foreground, _ = np.histogram(probability[reference > 0], bins=edges)
    background, _ = np.histogram(probability[reference <= 0], bins=edges)
    return [{"lower_inclusive": float(edges[index]), "upper": float(edges[index + 1]),
             "upper_inclusive": index == bins - 1,
             "reference_foreground": int(foreground[index]), "reference_background": int(background[index])}
            for index in range(bins)]


def input_paths(handoff, run):
    # No recursive dataset discovery and no model deserialization.
    paths = {"checksum_manifest": handoff / "SHA256SUMS.txt"}
    for line in paths["checksum_manifest"].read_text(encoding="utf-8").splitlines():
        expected, relative = line.split(maxsplit=1)
        path = (handoff / relative).resolve()
        require(path.is_relative_to(handoff) and path.is_file(), "Unsafe or missing handoff manifest entry")
        if path.name.endswith((".nii", ".nii.gz")):
            require(relative in {"sample/case_851_ct.nii.gz", "sample/case_851_reference_mask.nii.gz"},
                    "Only supplied validation case 851 may be read")
        paths[relative] = path
    paths.update({name: run / name for name in ("metadata.json", "verification.json", "probabilities.nii.gz", "prediction_mask.nii.gz")})
    require(all(path.is_file() for path in paths.values()), "Required saved-run file missing")
    return paths


def validate_provenance(paths, hashes, metadata, handoff_metadata):
    for line in paths["checksum_manifest"].read_text(encoding="utf-8").splitlines():
        expected, relative = line.split(maxsplit=1)
        require(hashes.get(relative) == expected, f"Handoff checksum mismatch: {relative}")
    require(hashes.get("model/artery_unet_10case_weighted_step700.pt") == CHECKPOINT_SHA256,
            "Original checkpoint checksum mismatch")
    for key, expected in {"architecture": "SmallUNet3D", "base_channels": 8, "parameter_count": 85177,
                          "checkpoint_step": 700, "checkpoint_sha256": CHECKPOINT_SHA256,
                          "patch_size": [64, 64, 64], "stride": 32, "threshold": .70,
                          "preprocessing": "clip [-200, 800], then (image + 200) / 1000"}.items():
        require(metadata.get(key) == expected, f"Saved run provenance mismatch: {key}")
    require(metadata.get("source_sha256") == hashes.get("sample/case_851_ct.nii.gz"), "Source checksum mismatch")
    require(handoff_metadata.get("sample_case_id") == 851 and handoff_metadata.get("sample_split") == "Validation"
            and 851 in handoff_metadata.get("validation_case_ids", [])
            and 851 not in handoff_metadata.get("training_case_ids", [])
            and handoff_metadata.get("test_cases_used") is False, "Validation-case provenance mismatch")


def write_csv(path, rows):
    with path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def audit(handoff, run, output, allow_unknown=False):
    handoff, run, output = handoff.resolve(), run.resolve(), output.resolve()
    repo = Path(__file__).resolve().parents[1]
    require(not output.is_relative_to(repo) and not output.is_relative_to(handoff) and not output.is_relative_to(run),
            "Reports must be outside the repository and original artifact directories")
    require(not output.exists(), "Output directory already exists; refusing to overwrite reports")
    paths = input_paths(handoff, run)
    print("Hashing original handoff and saved-run inputs...", flush=True)
    initial_hashes = {name: sha256(path) for name, path in paths.items()}
    metadata = json.loads(paths["metadata.json"].read_text())
    handoff_metadata = json.loads(paths["handoff_metadata.json"].read_text())
    verification = json.loads(paths["verification.json"].read_text())
    validate_provenance(paths, initial_hashes, metadata, handoff_metadata)
    images = {"ct": nib.load(paths["sample/case_851_ct.nii.gz"]),
              "reference": nib.load(paths["sample/case_851_reference_mask.nii.gz"]),
              "probabilities": nib.load(paths["probabilities.nii.gz"]), "prediction": nib.load(paths["prediction_mask.nii.gz"])}
    geometry = validate_geometry(images, metadata, allow_unknown)
    print("Geometry accepted. Reading saved arrays only...", flush=True)
    ct = np.asanyarray(images["ct"].dataobj)
    reference_values = np.asanyarray(images["reference"].dataobj)
    # Preserve original float64 label > 0 semantics before releasing the large raw array.
    require(np.isfinite(reference_values).all(), "Non-finite reference values")
    reference = reference_values > 0
    del reference_values
    probability = np.asanyarray(images["probabilities"].dataobj)
    prediction = np.asanyarray(images["prediction"].dataobj)
    validate_arrays(probability, prediction, reference, ct)
    prediction = prediction > 0
    metrics = [dict(threshold=threshold, **confusion(probability >= threshold, reference)) for threshold in THRESHOLDS]
    baseline = metrics[2]
    require(baseline["predicted_foreground"] == metadata.get("foreground_voxels") == verification.get("foreground_voxels"),
            "Saved foreground counts mismatch")
    require(baseline["reference_foreground"] == verification.get("reference_foreground_voxels")
            and baseline["tp"] == verification.get("intersection_voxels")
            and np.isclose(baseline["dice"], verification.get("dice_recomputed"), rtol=0, atol=1e-12),
            "Existing verification metrics mismatch")
    print("Computing sparse 6-connected components...", flush=True)
    components = connected_components(prediction, reference)
    component_report = component_summary(components)
    require(sum(row["voxels"] for row in components) == baseline["predicted_foreground"]
            and sum(row["tp"] for row in components) == baseline["tp"]
            and sum(row["fp"] for row in components) == baseline["fp"], "Component totals mismatch")
    histogram = probability_histogram(probability, reference)
    require(sum(row["reference_foreground"] + row["reference_background"] for row in histogram) == probability.size,
            "Histogram totals mismatch")
    groups = {}
    for name, selector in (("reference_foreground", reference), ("reference_background", ~reference),
                           ("tp_at_070", prediction & reference), ("fp_at_070", prediction & ~reference),
                           ("fn_at_070", ~prediction & reference)):
        intensities = ct[selector]
        groups[name] = {"probability": distribution(probability[selector]), "ct_intensity": distribution(intensities),
                        "ct_below_minus200": int(np.count_nonzero(intensities < -200)),
                        "ct_above_800": int(np.count_nonzero(intensities > 800))}
    slices = [dict(array_axis=2, slice_index=k, **confusion(prediction[:, :, k], reference[:, :, k])) for k in range(ct.shape[2])]
    print("Rehashing all original inputs to verify read-only integrity...", flush=True)
    final_hashes = {name: sha256(path) for name, path in paths.items()}
    require(initial_hashes == final_hashes, "Original inputs changed during audit; refusing to publish results")
    summary = {
        "case_id": 851, "split": "validation", "created_utc": datetime.now(timezone.utc).isoformat(),
        "research_only": True, "alignment_assumption": ALIGNMENT_NOTE if geometry["reference"]["units"][0] == "unknown" else "All spatial units match mm.",
        "unknown_reference_units_explicitly_allowed": allow_unknown, "geometry": geometry,
        "provenance": {"metadata": metadata, "verification": verification,
                       "inputs": {name: {"path": str(path), "sha256_before": initial_hashes[name], "sha256_after": final_hashes[name]}
                                  for name, path in paths.items()}, "all_input_hashes_unchanged": True,
                       "limitation": "Run metadata attests checkpoint linkage; saved probability/mask files have no independent signed generation provenance."},
        "environment": {"python": sys.version, "executable": sys.executable, "platform": platform.platform(),
                        "versions": {name: importlib.metadata.version(name) for name in ("numpy", "nibabel", "pytest")}},
        "thresholds": metrics, "components_at_070": component_report, "distributions": groups,
        "slices_with_fp_at_070": sum(row["fp"] > 0 for row in slices),
        "max_fp_slice_at_070": max(slices, key=lambda row: row["fp"]),
        "metric_conventions": "Whole-volume counts; reference label > 0; prediction probability >= threshold; zero denominators are null/undefined, not 1 or 0.",
        "script_sha256": sha256(Path(__file__).resolve()),
        "limits": ["Single validation case, no final threshold selection or cross-case generalization.",
                   "No inference, training, postprocessing, medical diagnosis or held-out test data access.",
                   "Components depend on 6-connectivity; zero reference overlap does not establish anatomical non-artery tissue.",
                   "Probability values are model scores, not calibrated clinical confidence.",
                   "CT scaled intensities follow the existing HU assumption; scanner calibration was not independently verified."],
    }
    output.mkdir(parents=True, exist_ok=False)
    (output / "audit.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    write_csv(output / "threshold-metrics.csv", metrics)
    write_csv(output / "components-070.csv", sorted(components, key=lambda row: (-row["voxels"], row["component_id"])))
    write_csv(output / "component-size-distribution.csv", component_report["size_bins"])
    write_csv(output / "probability-histogram.csv", histogram)
    write_csv(output / "slice-counts-070.csv", slices)
    print(json.dumps({"output": str(output), "thresholds": metrics, "components_at_070": component_report}, indent=2), flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff-dir", required=True, type=Path)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--allow-reference-unknown-units", action="store_true")
    args = parser.parse_args()
    try:
        audit(args.handoff_dir, args.run_dir, args.output_dir, args.allow_reference_unknown_units)
    except (AuditError, OSError, ValueError, KeyError, nib.filebasedimages.ImageFileError) as error:
        parser.exit(1, f"Audit stopped without a success claim: {error}\n")


if __name__ == "__main__":
    main()
