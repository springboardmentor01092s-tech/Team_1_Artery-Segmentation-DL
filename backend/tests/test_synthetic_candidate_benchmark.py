"""Controlled synthetic candidate-extraction checks; no real images or DB."""
import hashlib

import numpy as np
import pytest

from app.services.synthetic_stenosis_ml import (
    DEFAULT_RESEARCH_SEVERITY_THRESHOLDS,
    generate_phantom,
    extract_synthetic_candidate_profile,
    provisional_research_severity,
    validate_research_severity_thresholds,
)
from app.services.synthetic_stenosis_validation import (
    _errors, _one_to_one_candidate_matches, benchmark_synthetic_measurements,
)


def test_error_summary_keeps_signed_bias_separate_from_absolute_error():
    summary = _errors([2.0, -1.0])
    assert summary["mae"] == 1.5
    assert summary["rmse"] == pytest.approx(np.sqrt(2.5))
    assert summary["bias"] == 0.5


def test_candidate_matching_maximizes_valid_pairs_before_nearest_distance():
    # Greedy nearest-neighbor assignment can consume the only viable target and
    # lose a second valid match. The benchmark must maximize cardinality first.
    matches = _one_to_one_candidate_matches([0.0, 2.0], [1.0, -1.0], tolerance=2.0)
    assert len(matches) == 2
    assert {(prediction, target) for prediction, target, _ in matches} == {(0, 1), (1, 0)}


def test_controlled_candidate_benchmark_across_class_orientation_and_noise():
    """Measure radii, narrowing, severity and localization vs withheld truth."""
    result = benchmark_synthetic_measurements()
    assert result["counts"]["cases"] == 180
    assert result["counts"]["normal_cases"] == 36
    assert result["counts"]["normal_false_candidates"] == 0
    assert result["counts"]["lesion_count"] == 216
    assert result["candidate_detection"]["precision"] >= 0.98
    assert result["candidate_detection"]["recall"] >= 0.95
    assert result["candidate_detection"]["multiple_lesion_recall"] >= 0.9
    errors = result["measurement_error"]
    assert errors["reference_radius_synthetic_voxels"]["mae"] < 0.45
    assert errors["minimum_radius_synthetic_voxels"]["mae"] < 0.35
    assert errors["percentage_narrowing_points"]["mae"] < 4.0
    assert errors["lesion_minimum_radius_synthetic_voxels"]["mae"] < 0.3
    assert errors["lesion_percentage_narrowing_points"]["mae"] < 3.0
    assert errors["lesion_localization_axial_voxels"]["mae"] < 0.5
    assert result["provisional_severity"]["profile_summary_all_cases"]["accuracy"] >= 0.9
    assert result["provisional_severity"]["matched_lesion_candidates_non_normal_classes"]["accuracy"] >= 0.95
    assert result["clinical_validation"] is False
    assert result["clinical_gate_authorized"] is False
    assert result["training_release_authorized"] is False


def test_estimator_does_not_read_opt_in_ground_truth():
    with_truth = generate_phantom(21, 3, 42, orientation_ijk=(1, 2, 3), include_geometry_ground_truth=True)
    without_truth = {**with_truth, "provenance": {
        key: value for key, value in with_truth["provenance"].items()
        if key != "synthetic_geometry_ground_truth"
    }}
    assert extract_synthetic_candidate_profile(with_truth) == extract_synthetic_candidate_profile(without_truth)


def test_provisional_severity_threshold_boundaries_and_configuration():
    assert DEFAULT_RESEARCH_SEVERITY_THRESHOLDS == (10.0, 30.0, 50.0, 70.0)
    assert [provisional_research_severity(value) for value in (0, 9.99, 10, 29.99, 30, 50, 70, 100)] == [
        "normal", "normal", "mild", "mild", "moderate", "severe", "critical_very_severe", "critical_very_severe",
    ]
    custom = (5.0, 25.0, 45.0, 65.0)
    assert provisional_research_severity(25, custom) == "moderate"
    for invalid in ((10, 30, 30, 70), (-1, 20, 40, 60), (10, 20, 40, 101), (10, 20, 30)):
        with pytest.raises(ValueError, match="threshold"):
            validate_research_severity_thresholds(invalid)


@pytest.mark.parametrize("axis", [(1, 1, 1), (-1, 2, 3), (3, -2, 1)])
def test_boundary_orientation_measurements_are_finite_and_bounded(axis):
    sample = generate_phantom(91, 4, 109, orientation_ijk=axis, noise_std=0.08,
                              multiple_narrowings=True, include_geometry_ground_truth=True)
    estimate = extract_synthetic_candidate_profile(sample)
    assert 0 < estimate["metrics"]["reference_radius_synthetic_units"] < 12
    for candidate in estimate["candidates"]:
        coordinates = candidate["location"]["center_ijk"]
        assert len(coordinates) == 3 and np.isfinite(coordinates).all()
        assert all(-1 <= coordinate <= 24 for coordinate in coordinates)
        measurements = candidate["measurements"]
        assert measurements["measurement_availability"] == "estimated_synthetic_only"
        assert measurements["measurement_confidence"] is None
        assert measurements["measurement_uncertainty"] is None
        assert 0 < measurements["minimum_radius_synthetic_units"] <= measurements["reference_radius_synthetic_units"]
        assert 0 <= measurements["estimated_percentage_narrowing_synthetic_only"] <= 100


def test_controlled_generator_truth_is_opt_in_and_does_not_change_volume():
    ordinary = generate_phantom(8, 2, 808)
    instrumented = generate_phantom(8, 2, 808, include_geometry_ground_truth=True)
    assert np.array_equal(ordinary["volume"], instrumented["volume"])
    assert ordinary["provenance"]["volume_sha256"] == instrumented["provenance"]["volume_sha256"]
    assert "synthetic_geometry_ground_truth" not in ordinary["provenance"]
    assert len(instrumented["provenance"]["synthetic_geometry_ground_truth"]["lesions"]) in (1, 2)


@pytest.mark.parametrize("bad_orientation", [(0, 0, 0), (float("nan"), 1, 0), (1, 2)])
def test_controlled_generator_rejects_invalid_orientations(bad_orientation):
    with pytest.raises(ValueError, match="orientation_ijk"):
        generate_phantom(1, 1, 2, orientation_ijk=bad_orientation)


def test_controlled_generator_rejects_invalid_noise_and_normal_multiple_lesions():
    with pytest.raises(ValueError, match="noise_std"):
        generate_phantom(1, 1, 2, noise_std=0.2)
    with pytest.raises(ValueError, match="normal phantoms"):
        generate_phantom(1, 0, 2, multiple_narrowings=True)


def test_candidate_extractor_rejects_altered_bytes_and_invalid_axis():
    sample = generate_phantom(2, 3, 91, include_geometry_ground_truth=True)
    changed = {**sample, "volume": sample["volume"].copy(), "provenance": dict(sample["provenance"])}
    changed["volume"][0, 0, 0] = np.float32(0.99)
    with pytest.raises(ValueError, match="source_hash"):
        extract_synthetic_candidate_profile(changed)

    bad_axis = {**sample, "provenance": dict(sample["provenance"])}
    bad_axis["provenance"]["axis_ijk"] = [0.0, 0.0, 0.0]
    bad_axis["provenance"]["volume_sha256"] = hashlib.sha256(sample["volume"].tobytes(order="C")).hexdigest()
    with pytest.raises(ValueError, match="provenance"):
        extract_synthetic_candidate_profile(bad_axis)
