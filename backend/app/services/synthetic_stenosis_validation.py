"""Reproducible evaluation helpers for controlled synthetic geometry only."""
from __future__ import annotations

from typing import Any

import numpy as np

from app.services.synthetic_stenosis_ml import (
    DEFAULT_RESEARCH_SEVERITY_THRESHOLDS,
    CLASS_NAMES,
    extract_synthetic_candidate_profile,
    generate_phantom,
    provisional_research_severity,
    validate_research_severity_thresholds,
)

ORIENTATIONS = ((1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 0), (1, 2, 3), (-2, 1, 2))
NOISE_LEVELS = (0.0, 0.025, 0.08)
LOCALIZATION_TOLERANCE_AXIAL_VOXELS = 2.8


def _one_to_one_candidate_matches(predicted: list[float], truth: list[float], tolerance: float):
    """Maximize valid match count, then minimize total axial distance."""
    if not predicted or not truth:
        return []
    from scipy.optimize import linear_sum_assignment

    distances = np.abs(np.asarray(predicted, dtype=float)[:, None] - np.asarray(truth, dtype=float)[None, :])
    max_matches = min(len(predicted), len(truth))
    unmatched_cost = (max_matches + 1) * (tolerance + 1.0)
    costs = np.full((len(predicted), len(truth) + len(predicted)), unmatched_cost, dtype=float)
    tie_break = np.fromfunction(lambda i, j: (i * (len(truth) + 1) + j) * 1e-12, distances.shape)
    valid = distances <= tolerance
    costs[:, :len(truth)] = np.where(valid, distances + tie_break, unmatched_cost * 2)
    rows, columns = linear_sum_assignment(costs)
    return [
        (int(row), int(column), float(distances[row, column]))
        for row, column in zip(rows, columns, strict=True)
        if column < len(truth) and valid[row, column]
    ]


def _errors(values: list[float]) -> dict[str, Any]:
    observed = np.asarray(values, dtype=float)
    if not observed.size:
        return {"n": 0, "mae": None, "rmse": None, "bias": None,
                "absolute_error_p50": None, "absolute_error_p90": None,
                "absolute_error_max": None}
    absolute = np.abs(observed)
    return {"n": int(observed.size), "mae": float(np.mean(absolute)),
            "rmse": float(np.sqrt(np.mean(np.square(observed)))),
            "bias": float(np.mean(observed)),
            "absolute_error_p50": float(np.percentile(absolute, 50)),
            "absolute_error_p90": float(np.percentile(absolute, 90)),
            "absolute_error_max": float(np.max(absolute))}


def _class_scores(truth: list[str], predicted: list[str], class_names=CLASS_NAMES) -> dict[str, Any]:
    matrix = np.zeros((len(class_names), len(class_names)), dtype=np.int64)
    index = {name: i for i, name in enumerate(class_names)}
    for actual, result in zip(truth, predicted, strict=True):
        matrix[index[actual], index[result]] += 1
    per_class = {}
    f1s = []
    for i, name in enumerate(class_names):
        tp = int(matrix[i, i]); fp = int(matrix[:, i].sum() - tp); fn = int(matrix[i, :].sum() - tp)
        support = int(matrix[i, :].sum())
        precision = tp / (tp + fp) if tp + fp else (0.0 if support else None)
        recall = tp / support if support else None
        f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall and precision + recall else (0.0 if support and precision is not None else None)
        per_class[name] = {"support": support, "precision": precision,
                           "recall": recall, "f1": f1}
        if f1 is not None:
            f1s.append(f1)
    return {"sample_count": len(truth),
            "accuracy": float(np.trace(matrix) / matrix.sum()) if matrix.sum() else None,
            "macro_f1": float(np.mean(f1s)) if f1s else None, "per_class": per_class,
            "confusion_matrix_rows_true_columns_predicted": matrix.tolist(),
            "class_order": list(class_names),
            "scope": "provisional_synthetic_severity_on_matched_candidates_only"}


def benchmark_synthetic_measurements(severity_thresholds=DEFAULT_RESEARCH_SEVERITY_THRESHOLDS) -> dict[str, Any]:
    """Evaluate estimates against opt-in generator truth, never passed to estimator."""
    thresholds = validate_research_severity_thresholds(severity_thresholds)
    error_values = {name: [] for name in (
        "reference_radius_synthetic_voxels", "minimum_radius_synthetic_voxels",
        "percentage_narrowing_points", "lesion_minimum_radius_synthetic_voxels",
        "lesion_percentage_narrowing_points", "lesion_localization_axial_voxels",
    )}
    class_truth: list[str] = []
    class_predicted: list[str] = []
    profile_class_truth: list[str] = []
    profile_class_predicted: list[str] = []
    counts = {"cases": 0, "normal_cases": 0, "normal_false_candidates": 0,
              "lesion_count": 0, "predicted_candidate_count": 0, "matched_lesion_count": 0,
              "multiple_lesion_count": 0, "matched_multiple_lesion_count": 0}

    for class_id in range(len(CLASS_NAMES)):
        for orientation_index, orientation in enumerate(ORIENTATIONS):
            for noise_index, noise in enumerate(NOISE_LEVELS):
                for replicate in range(2):
                    sample_id = 100_000 + class_id * 1000 + orientation_index * 100 + noise_index * 10 + replicate
                    seed = 41_000 + class_id * 71 + orientation_index * 13 + replicate
                    multiple = class_id > 0 and replicate == 1
                    sample = generate_phantom(
                        sample_id, class_id, seed, orientation_ijk=orientation,
                        noise_std=noise, multiple_narrowings=multiple,
                        include_geometry_ground_truth=True,
                    )
                    # The estimator receives volume and ordinary provenance only.
                    # Independent generator truth is extracted after estimation.
                    estimator_input = {**sample, "provenance": {
                        key: value for key, value in sample["provenance"].items()
                        if key in {"source", "generator_version", "sample_id", "seed", "volume_sha256", "axis_ijk"}
                    }, "label": None}
                    estimate = extract_synthetic_candidate_profile(
                        estimator_input, severity_thresholds=thresholds,
                    )
                    truth = sample["provenance"]["synthetic_geometry_ground_truth"]
                    counts["cases"] += 1
                    reference_error = estimate["metrics"]["reference_radius_synthetic_units"] - truth["nominal_radius_voxels"]
                    minimum_error = estimate["metrics"]["minimum_radius_synthetic_units"] - truth["nominal_minimum_radius_voxels"]
                    narrowing_error = estimate["metrics"]["estimated_percentage_narrowing_synthetic_only"] - truth["nominal_percentage_narrowing"]
                    error_values["reference_radius_synthetic_voxels"].append(float(reference_error))
                    error_values["minimum_radius_synthetic_voxels"].append(float(minimum_error))
                    error_values["percentage_narrowing_points"].append(float(narrowing_error))
                    profile_class_truth.append(provisional_research_severity(
                        truth["nominal_percentage_narrowing"], thresholds))
                    profile_class_predicted.append(estimate["metrics"]["provisional_severity_synthetic_only"])

                    lesions = truth["lesions"]
                    candidates = estimate["candidates"]
                    counts["lesion_count"] += len(lesions)
                    counts["predicted_candidate_count"] += len(candidates)
                    if not lesions:
                        counts["normal_cases"] += 1
                        counts["normal_false_candidates"] += len(candidates)
                    if len(lesions) > 1:
                        counts["multiple_lesion_count"] += len(lesions)

                    center = np.asarray(truth["phantom_center_ijk"], dtype=float)
                    axis = np.asarray(sample["provenance"]["axis_ijk"], dtype=float)
                    truth_centers = [float(item["center_axial_voxels"]) for item in lesions]
                    predicted_centers = [float((np.asarray(item["location"]["center_ijk"]) - center) @ axis)
                                         for item in candidates]
                    # Deterministic maximum-cardinality, minimum-distance assignment;
                    # every prediction and truth can contribute at most once.
                    for candidate_index, truth_index, _ in _one_to_one_candidate_matches(
                        predicted_centers, truth_centers, LOCALIZATION_TOLERANCE_AXIAL_VOXELS,
                    ):
                        candidate = candidates[candidate_index]
                        signed_location_error = predicted_centers[candidate_index] - truth_centers[truth_index]
                        lesion = lesions[truth_index]
                        measured = candidate["measurements"]
                        error_values["lesion_localization_axial_voxels"].append(float(signed_location_error))
                        error_values["lesion_minimum_radius_synthetic_voxels"].append(
                            measured["minimum_radius_synthetic_units"] - lesion["minimum_radius_voxels"])
                        error_values["lesion_percentage_narrowing_points"].append(
                            measured["estimated_percentage_narrowing_synthetic_only"] - lesion["percentage_narrowing"])
                        class_truth.append(provisional_research_severity(lesion["percentage_narrowing"], thresholds))
                        class_predicted.append(measured["severity_synthetic_only"])
                        counts["matched_lesion_count"] += 1
                        if len(lesions) > 1:
                            counts["matched_multiple_lesion_count"] += 1

    matches = counts["matched_lesion_count"]
    candidates = counts["predicted_candidate_count"]
    lesions = counts["lesion_count"]
    return {
        "schema_version": "synthetic-geometry-measurement-benchmark/0.1",
        "scope": "controlled_synthetic_generator_geometry_only_not_clinical_validation",
        "matrix": {"class_count": 5, "orientations_ijk": [list(axis) for axis in ORIENTATIONS],
                   "noise_std": list(NOISE_LEVELS), "replicates_per_configuration": 2,
                   "localization_tolerance_axial_voxels": LOCALIZATION_TOLERANCE_AXIAL_VOXELS},
        "counts": counts,
        "candidate_detection": {"precision": matches / candidates if candidates else 0.0,
                                 "recall": matches / lesions if lesions else 0.0,
                                 "multiple_lesion_recall": counts["matched_multiple_lesion_count"] / counts["multiple_lesion_count"] if counts["multiple_lesion_count"] else None},
        "measurement_error": {name: _errors(values) for name, values in error_values.items()},
        "provisional_severity": {
            "profile_summary_all_cases": _class_scores(profile_class_truth, profile_class_predicted),
            "matched_lesion_candidates_non_normal_classes": _class_scores(
                class_truth, class_predicted, CLASS_NAMES),
        },
        "severity_thresholds_percent": list(thresholds),
        "clinical_validation": False,
        "clinical_gate_authorized": False,
        "training_release_authorized": False,
    }
