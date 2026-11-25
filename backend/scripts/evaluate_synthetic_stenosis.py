"""Re-evaluate a frozen synthetic-only checkpoint on a new seeded phantom set.

No CT, case database, patient data, model training, or clinical labels are used.
Writes summary/CSV artifacts only; never overwrites an existing output directory.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.synthetic_stenosis_ml import (
    CLASS_NAMES,
    extract_synthetic_candidate_profile,
    generate_phantom,
    load_verified_checkpoint,
    make_splits,
    predict_synthetic,
)

SAMPLE_ID_BASE = 100_000
SAMPLE_SEED_STRIDE = 7_919
LOCALIZATION_TOLERANCE_VOXELS = 2.8
BASELINE_CLASS_BOUNDARIES = (0.075, 0.315, 0.515, 0.715)


def classification_metrics(truth: list[int], predicted: list[int]) -> dict[str, Any]:
    confusion = np.zeros((len(CLASS_NAMES), len(CLASS_NAMES)), dtype=np.int64)
    for actual, result in zip(truth, predicted, strict=True):
        confusion[actual, result] += 1
    rows = {}
    f1_values = []
    for class_id, name in enumerate(CLASS_NAMES):
        tp = int(confusion[class_id, class_id])
        fp = int(confusion[:, class_id].sum() - tp)
        fn = int(confusion[class_id, :].sum() - tp)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        rows[name] = {"support": int(confusion[class_id, :].sum()), "precision": precision,
                      "recall": recall, "f1": f1}
        f1_values.append(f1)
    return {
        "sample_count": len(truth),
        "accuracy": float(np.mean(np.asarray(truth) == np.asarray(predicted))) if truth else None,
        "macro_precision": float(np.mean([row["precision"] for row in rows.values()])),
        "macro_recall": float(np.mean([row["recall"] for row in rows.values()])),
        "macro_f1": float(np.mean(f1_values)),
        "per_class": rows,
        "confusion_matrix_rows_true_columns_predicted": confusion.tolist(),
        "class_order": list(CLASS_NAMES),
    }


def _baseline_class(geometry: dict[str, Any]) -> int:
    candidates = geometry["candidates"]
    if not candidates:
        return 0
    reductions = [
        item["measurements"]["estimated_percentage_narrowing_synthetic_only"] / 100.0
        for item in candidates
        if item["measurements"]["estimated_percentage_narrowing_synthetic_only"] is not None
    ]
    if not reductions:
        return 0
    value = max(reductions)
    return int(np.searchsorted(BASELINE_CLASS_BOUNDARIES, value, side="right"))


def _match_candidate_centers(predicted: list[float], truth: list[float]) -> list[float]:
    unmatched = set(range(len(truth)))
    errors = []
    for candidate in predicted:
        if not unmatched:
            break
        index = min(unmatched, key=lambda item: abs(candidate - truth[item]))
        error = abs(candidate - truth[index])
        if error <= LOCALIZATION_TOLERANCE_VOXELS:
            errors.append(error)
            unmatched.remove(index)
    return errors


def _write_json(path: Path, value: Any):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def evaluate(checkpoint: str, checkpoint_sha256: str, output_dir: str | Path,
             sample_count: int = 500, dataset_seed: int = 2_026_112_600) -> dict[str, Any]:
    if type(sample_count) is not int or sample_count < 100 or sample_count % 5:
        raise ValueError("sample_count must be a multiple of five and at least 100")
    if type(dataset_seed) is not int or dataset_seed < 0:
        raise ValueError("dataset_seed must be a nonnegative integer")
    model, checkpoint_metadata, verified_checkpoint_sha = load_verified_checkpoint(checkpoint, checkpoint_sha256)
    if checkpoint_metadata["seed"] == dataset_seed:
        raise ValueError("evaluation dataset seed must differ from checkpoint training seed")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)

    import torch
    torch.set_num_threads(min(2, torch.get_num_threads()))
    split_seed = dataset_seed + 1
    splits = make_splits(sample_count, split_seed)
    split_sets = {name: set(values) for name, values in splits.items()}
    if any(split_sets[a] & split_sets[b] for a in splits for b in splits if a < b):
        raise RuntimeError("synthetic evaluation split leakage detected")

    samples = []
    dataset_records = []
    for local_id in range(sample_count):
        class_id = local_id % len(CLASS_NAMES)
        sample_id = SAMPLE_ID_BASE + local_id
        sample_seed = dataset_seed + local_id * SAMPLE_SEED_STRIDE
        sample = generate_phantom(sample_id, class_id, sample_seed, include_geometry_ground_truth=True)
        samples.append(sample)
        dataset_records.append({"sample_id": sample_id, "class_id": class_id,
                                "split_local_id": local_id, "seed": sample_seed,
                                "volume_sha256": sample["provenance"]["volume_sha256"]})

    sample_hashes = [item["volume_sha256"] for item in dataset_records]
    if len(sample_hashes) != len(set(sample_hashes)):
        raise RuntimeError("duplicate synthetic volume hashes detected")
    dataset_digest = hashlib.sha256(json.dumps(dataset_records, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    prior_split = checkpoint_metadata["split_sample_ids"]
    prior_train_local_ids = [int(value) for value in prior_split["train"]]
    prior_train_hashes = set()
    for old_id in prior_train_local_ids:
        old_class = old_id % len(CLASS_NAMES)
        old_seed = int(checkpoint_metadata["seed"]) + old_id * SAMPLE_SEED_STRIDE
        old_sample = generate_phantom(old_id, old_class, old_seed)
        prior_train_hashes.add(old_sample["provenance"]["volume_sha256"])
    test_hashes = {dataset_records[index]["volume_sha256"] for index in splits["test"]}
    overlap = test_hashes & prior_train_hashes
    if overlap:
        raise RuntimeError("new evaluation test data overlaps checkpoint training inputs")

    class_counts = {
        split: dict(sorted(Counter(CLASS_NAMES[local_id % len(CLASS_NAMES)] for local_id in local_ids).items()))
        for split, local_ids in splits.items()
    }
    split_records = {
        split: [SAMPLE_ID_BASE + local_id for local_id in local_ids]
        for split, local_ids in splits.items()
    }
    dataset_manifest = {
        "schema_version": "synthetic-stenosis-evaluation-dataset/0.1",
        "generator_id": samples[0]["provenance"]["source"],
        "generator_version": samples[0]["provenance"]["generator_version"],
        "dataset_seed": dataset_seed,
        "split_seed": split_seed,
        "sample_count": sample_count,
        "sample_id_range": [SAMPLE_ID_BASE, SAMPLE_ID_BASE + sample_count - 1],
        "class_distribution": dict(sorted(Counter(item["label"] for item in samples).items())),
        "class_names": list(CLASS_NAMES),
        "split_counts": {name: len(ids) for name, ids in split_records.items()},
        "split_class_counts": class_counts,
        "disjoint_split_ids": True,
        "unique_volume_hashes": True,
        "checkpoint_training_hash_overlap": len(overlap),
        "dataset_sha256_of_sample_identity_manifest": dataset_digest,
        "split_sample_ids": split_records,
        "training_and_validation_use": "reserved_only; frozen checkpoint not retrained",
    }
    _write_json(output / "dataset-manifest.json", dataset_manifest)

    test_ids = splits["test"]
    truth = [samples[index]["label"] for index in test_ids]
    model_predictions = []
    baseline_predictions = []
    candidate_truth_total = candidate_pred_total = candidate_tp_total = 0
    localization_errors = []
    case_rows = []
    for local_id in test_ids:
        sample = samples[local_id]
        prediction = predict_synthetic(model, sample)
        model_class = CLASS_NAMES.index(prediction["class"])
        geometry = extract_synthetic_candidate_profile(sample)
        baseline_class = _baseline_class(geometry)
        model_predictions.append(model_class)
        baseline_predictions.append(baseline_class)

        hidden = sample["provenance"]["synthetic_geometry_ground_truth"]
        axis = np.asarray(sample["provenance"]["axis_ijk"], dtype=float)
        center = np.asarray(hidden["phantom_center_ijk"], dtype=float)
        truth_centers = [float(lesion["center_axial_voxels"]) for lesion in hidden["lesions"]]
        predicted_centers = [
            float((np.asarray(candidate["location"]["center_ijk"]) - center) @ axis)
            for candidate in geometry["candidates"]
        ]
        errors = _match_candidate_centers(predicted_centers, truth_centers)
        candidate_truth_total += len(truth_centers)
        candidate_pred_total += len(predicted_centers)
        candidate_tp_total += len(errors)
        localization_errors.extend(errors)
        case_rows.append({
            "sample_id": sample["sample_id"],
            "true_synthetic_class": CLASS_NAMES[sample["label"]],
            "model_synthetic_class": CLASS_NAMES[model_class],
            "geometry_baseline_class": CLASS_NAMES[baseline_class],
            "truth_lesion_count": len(truth_centers),
            "predicted_candidate_count": len(predicted_centers),
            "matched_candidate_count": len(errors),
            "matched_localization_errors_axial_voxels": ";".join(f"{x:.6f}" for x in errors),
            "volume_sha256": sample["provenance"]["volume_sha256"],
        })

    for result_name, rows in (("model", model_predictions), ("geometry_baseline", baseline_predictions)):
        metrics = classification_metrics(truth, rows)
        metrics["scope"] = "synthetic_new_test_split_only"
        metrics["clinical_performance_claim"] = False
        if result_name == "model":
            model_metrics = metrics
        else:
            baseline_metrics = metrics

    candidate_metrics = {
        "synthetic_test_lesion_count": candidate_truth_total,
        "predicted_candidate_count": candidate_pred_total,
        "matched_count_within_2_8_axial_voxels": candidate_tp_total,
        "localization_tolerance_axial_voxels": LOCALIZATION_TOLERANCE_VOXELS,
        "precision": candidate_tp_total / candidate_pred_total if candidate_pred_total else 0.0,
        "recall": candidate_tp_total / candidate_truth_total if candidate_truth_total else 0.0,
        "mean_absolute_localization_error_axial_voxels": float(np.mean(localization_errors)) if localization_errors else None,
        "scope": "controlled_synthetic_generator_geometry_only",
    }
    with (output / "test-cases.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(case_rows[0]))
        writer.writeheader()
        writer.writerows(case_rows)

    report = {
        "schema_version": "synthetic-stenosis-evaluation/0.1",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "checkpoint_sha256": verified_checkpoint_sha,
        "checkpoint_model": checkpoint_metadata["model_id"],
        "checkpoint_model_version": checkpoint_metadata["model_version"],
        "checkpoint_training_seed": checkpoint_metadata["seed"],
        "dataset_sha256": dataset_digest,
        "model_test_metrics": model_metrics,
        "simple_geometry_baseline_test_metrics": baseline_metrics,
        "candidate_localization_metrics": candidate_metrics,
        "limitations": [
            "All samples are scalar synthetic phantoms, not CT or anatomy.",
            "The frozen model was not retrained on this evaluation dataset.",
            "The geometry baseline uses synthetic voxel-space estimates and generator-specified axis; it is not a clinical method.",
            "These measurements do not establish clinical performance, validated stenosis, or patient generalization.",
        ],
        "clinical_validation": False,
        "clinical_gate_authorized": False,
        "training_release_authorized": False,
    }
    _write_json(output / "evaluation-report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--checkpoint-sha256", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--samples", type=int, default=500)
    parser.add_argument("--seed", type=int, default=2_026_112_600)
    args = parser.parse_args()
    result = evaluate(args.checkpoint, args.checkpoint_sha256, args.output_dir, args.samples, args.seed)
    print(json.dumps({
        "output_dir": str(Path(args.output_dir).resolve()),
        "dataset_sha256": result["dataset_sha256"],
        "model_macro_f1": result["model_test_metrics"]["macro_f1"],
        "baseline_macro_f1": result["simple_geometry_baseline_test_metrics"]["macro_f1"],
        "candidate_precision": result["candidate_localization_metrics"]["precision"],
        "candidate_recall": result["candidate_localization_metrics"]["recall"],
        "clinical_gate_authorized": False,
        "training_release_authorized": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
