from copy import deepcopy

import nibabel as nib
import numpy as np
import pytest

from research.baseline_false_positive_audit import (
    AuditError, CHECKPOINT_SHA256, audit, component_summary, confusion,
    connected_components, probability_histogram, validate_arrays,
    validate_geometry, validate_provenance,
)


def geometry_fixture():
    images = {}
    for name in ("ct", "reference", "probabilities", "prediction"):
        image = nib.Nifti1Image(np.zeros((3, 4, 5), dtype=np.float32), np.diag([-.5, .5, 1, 1]))
        image.header.set_xyzt_units("mm")
        images[name] = image
    ct = images["ct"]
    return images, {"shape": list(ct.shape), "affine": ct.affine.tolist(), "xyzt_units": 2}


def test_geometry_accepts_matching_signed_affine_without_resampling():
    images, metadata = geometry_fixture()
    geometry = validate_geometry(images, metadata)
    assert geometry["ct"]["axis_codes"] == ["L", "A", "S"]
    assert geometry["ct"]["spacing"] == [.5, .5, 1]


def test_unknown_reference_units_require_explicit_opt_in_and_are_not_modified():
    images, metadata = geometry_fixture()
    images["reference"].header.set_xyzt_units("unknown")
    with pytest.raises(AuditError, match="opt-in"):
        validate_geometry(images, metadata)
    assert validate_geometry(images, metadata, True)["reference"]["units"][0] == "unknown"
    assert images["reference"].header.get_xyzt_units()[0] == "unknown"


@pytest.mark.parametrize("mismatch", ["shape", "affine", "spacing", "units", "uncoded", "nan"])
def test_geometry_mismatches_fail_even_with_unknown_units_override(mismatch):
    images, metadata = geometry_fixture()
    image = images["reference"]
    if mismatch == "shape":
        images["reference"] = nib.Nifti1Image(np.zeros((4, 4, 5)), image.affine)
    elif mismatch == "affine":
        image.affine[0, 3] += 1
    elif mismatch == "spacing":
        image.header.set_zooms((.6, .5, 1))
    elif mismatch == "units":
        image.header.set_xyzt_units("meter")
    elif mismatch == "uncoded":
        image.header["sform_code"] = image.header["qform_code"] = 0
    else:
        image.affine[0, 0] = np.nan
    with pytest.raises(AuditError):
        validate_geometry(images, metadata, True)


@pytest.mark.parametrize("field", ["shape", "affine", "xyzt_units"])
def test_run_geometry_metadata_mismatch_fails(field):
    images, metadata = geometry_fixture()
    metadata[field] = {"shape": [3, 4, 6], "affine": np.eye(4).tolist(), "xyzt_units": 0}[field]
    with pytest.raises(AuditError, match="metadata"):
        validate_geometry(images, metadata)


def test_confusion_metrics_are_hand_computed_and_labels_are_positive_not_equal_one():
    result = confusion(np.array([1, 1, 0, 0]), np.array([2, 0, 3, -1]))
    assert [result[name] for name in ("tp", "fp", "fn", "tn")] == [1, 1, 1, 1]
    assert result["dice"] == result["precision"] == result["recall"] == .5
    assert result["iou"] == 1 / 3
    assert result["undefined_metrics"] == []
    tiny = np.array([np.nextafter(0., 1.)], dtype=np.float64)
    assert confusion(np.ones(1), tiny)["tp"] == 1


@pytest.mark.parametrize("prediction,reference,undefined", [
    ([0, 0], [0, 0], ["dice", "iou", "precision", "recall"]),
    ([0, 0], [1, 0], ["precision"]),
    ([1, 0], [0, 0], ["recall"]),
])
def test_empty_denominators_are_explicitly_undefined(prediction, reference, undefined):
    result = confusion(np.array(prediction), np.array(reference))
    assert result["undefined_metrics"] == undefined
    assert all(result[name] is None for name in undefined)


@pytest.mark.parametrize("bad", [np.nan, np.inf, -.001, 1.001])
def test_invalid_probabilities_fail(bad):
    with pytest.raises(AuditError, match="Probabilities"):
        validate_arrays(np.array([bad]), np.zeros(1), np.zeros(1), np.zeros(1))


def test_saved_prediction_must_match_inclusive_float32_threshold_exactly():
    probability = np.array([.5, .6, .7, .8], dtype=np.float32)
    saved = np.array([0, 0, 1, 1])
    validate_arrays(probability, saved, saved, np.zeros(4))
    assert [confusion(probability >= threshold, saved)["predicted_foreground"]
            for threshold in (.5, .6, .7, .8)] == [4, 3, 2, 1]
    with pytest.raises(AuditError, match="differs"):
        validate_arrays(probability, np.zeros(4), saved, np.zeros(4))
    with pytest.raises(AuditError, match="binary"):
        validate_arrays(probability, np.array([0, 0, 2, 1]), saved, np.zeros(4))


@pytest.mark.parametrize("target", ["ct", "reference", "shape"])
def test_invalid_array_data_fails(target):
    probability, saved, reference, ct = (np.zeros(4) for _ in range(4))
    if target == "ct": ct[0] = np.nan
    elif target == "reference": reference[0] = np.nan
    else: saved = np.zeros(3)
    with pytest.raises(AuditError):
        validate_arrays(probability, saved, reference, ct)


def test_components_separate_islands_and_mixed_overlap_with_exact_totals():
    prediction = np.zeros((5, 4, 3), dtype=bool)
    reference = np.zeros_like(prediction)
    for voxel in ((0, 0, 0), (1, 0, 0), (1, 1, 0), (4, 3, 2), (4, 0, 0)):
        prediction[voxel] = True
    reference[0, 0, 0] = reference[4, 0, 0] = True
    rows = connected_components(prediction, reference)
    report = component_summary(rows)
    assert report["count"] == 3
    assert report["largest"]["voxels"] == 3
    assert report["largest"]["fraction_of_foreground"] == 3 / 5
    assert report["groups"]["zero_reference_overlap"]["fp"] == 1
    assert report["groups"]["mixed_tp_fp"]["fp"] == 2
    assert report["groups"]["all_tp"]["tp"] == 1
    assert sum(row["tp"] for row in rows) == 2
    assert sum(row["fp"] for row in rows) == 3


@pytest.mark.parametrize("voxels", [
    ((0, 0, 0), (1, 1, 1)),  # Corner contact is not a face.
    ((0, 0, 2), (0, 1, 0)),  # Flat +/-1 must not wrap a row.
    ((0, 1, 0), (1, 0, 0)),  # Flat +/-nz must not wrap a plane.
])
def test_components_use_faces_only_and_never_wrap(voxels):
    prediction = np.zeros((2, 2, 3), dtype=bool)
    for voxel in voxels: prediction[voxel] = True
    assert len(connected_components(prediction, np.zeros_like(prediction))) == 2


def test_empty_component_summary_is_defined_without_invented_fractions():
    rows = connected_components(np.zeros((2, 2, 2)), np.zeros((2, 2, 2)))
    report = component_summary(rows)
    assert rows == [] and report["count"] == 0 and report["largest"] is None
    assert report["size_distribution"]["mean"] is None


def test_histogram_counts_partition_reference_and_include_probability_one():
    rows = probability_histogram(np.array([0., .25, .5, 1.]), np.array([1, 1, 0, 0]), bins=2)
    assert [row["reference_foreground"] for row in rows] == [2, 0]
    assert [row["reference_background"] for row in rows] == [0, 2]
    assert rows[-1]["upper_inclusive"] is True


def provenance_fixture(tmp_path):
    manifest = tmp_path / "SHA256SUMS.txt"
    manifest.write_text(f"{CHECKPOINT_SHA256}  model/artery_unet_10case_weighted_step700.pt\nct-hash  sample/case_851_ct.nii.gz\n")
    hashes = {"model/artery_unet_10case_weighted_step700.pt": CHECKPOINT_SHA256, "sample/case_851_ct.nii.gz": "ct-hash"}
    metadata = {"architecture": "SmallUNet3D", "base_channels": 8, "parameter_count": 85177,
                "checkpoint_step": 700, "checkpoint_sha256": CHECKPOINT_SHA256, "source_sha256": "ct-hash",
                "patch_size": [64] * 3, "stride": 32, "threshold": .7,
                "preprocessing": "clip [-200, 800], then (image + 200) / 1000"}
    handoff = {"sample_case_id": 851, "sample_split": "Validation", "validation_case_ids": [851],
               "training_case_ids": [251], "test_cases_used": False}
    return {"checksum_manifest": manifest}, hashes, metadata, handoff


@pytest.mark.parametrize("field", ["checkpoint_sha256", "source_sha256", "stride", "threshold"])
def test_changed_run_provenance_fails_closed(tmp_path, field):
    paths, hashes, metadata, handoff = provenance_fixture(tmp_path)
    validate_provenance(paths, hashes, metadata, handoff)
    metadata = deepcopy(metadata)
    metadata[field] = "wrong"
    with pytest.raises(AuditError):
        validate_provenance(paths, hashes, metadata, handoff)


def test_handoff_hash_or_validation_identity_mismatch_fails(tmp_path):
    paths, hashes, metadata, handoff = provenance_fixture(tmp_path)
    hashes["sample/case_851_ct.nii.gz"] = "wrong"
    with pytest.raises(AuditError, match="checksum mismatch"):
        validate_provenance(paths, hashes, metadata, handoff)
    hashes["sample/case_851_ct.nii.gz"] = "ct-hash"
    handoff["sample_split"] = "Test"
    with pytest.raises(AuditError, match="Validation-case"):
        validate_provenance(paths, hashes, metadata, handoff)


def test_existing_output_directory_is_never_overwritten(tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("preserve")
    with pytest.raises(AuditError, match="already exists"):
        audit(tmp_path / "missing-handoff", tmp_path / "missing-run", output)
    assert marker.read_text() == "preserve"


def test_output_inside_repository_is_rejected():
    from pathlib import Path
    with pytest.raises(AuditError, match="outside"):
        audit(Path("missing"), Path("missing-run"), Path(__file__).parent / "never-created")
