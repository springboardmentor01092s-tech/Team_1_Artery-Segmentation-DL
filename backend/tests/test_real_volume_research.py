import hashlib

import numpy as np
import pytest

from app.services.real_volume_research import RealVolumeResearchError, analyze_real_volume_arrays


def _digest(character):
    return hashlib.sha256(character.encode()).hexdigest()


def _pair(shape=(32, 32, 32), affine=None, mask_affine=None, units="mm", mask_units="mm"):
    affine = np.asarray(affine if affine is not None else [
        [0.5, 0, 0, -8], [0, 0.7, 0, -10], [0, 0, 1.2, -20], [0, 0, 0, 1],
    ], dtype=float)
    mask_affine = affine if mask_affine is None else np.asarray(mask_affine, dtype=float)
    ct = np.zeros(shape, dtype=np.int16)
    mask = np.zeros(shape, dtype=np.uint8)
    mask[8:24, 14:18, 14:18] = 1
    return analyze_real_volume_arrays(ct, mask, affine, mask_affine, ct_units=units,
                                      mask_units=mask_units, ct_sha256=_digest("ct"),
                                      mask_file_sha256=_digest("mask"))


def test_valid_pair_preserves_geometry_and_abstains_on_unverified_lumen_semantics():
    result = _pair()
    assert result["status"] == "profile_only"
    assert result["geometry"]["shape_ijk"] == [32, 32, 32]
    assert result["geometry"]["voxel_spacing_mm"] == pytest.approx([0.5, 0.7, 1.2])
    assert result["geometry"]["orientation"] == ["R", "A", "S"]
    assert result["segmentation"]["component_count_26"] == 1
    assert result["centerline"]["status"] in {"experimental_tree", "abstained"}
    assert result["candidates"] == []
    assert result["candidate_status"] == "unavailable_mask_semantics_unverified"
    assert result["measurements"]["estimated_percentage_narrowing"] is None
    assert result["clinical_gate_authorized"] is False
    assert result["training_release_authorized"] is False
    assert result["provenance"]["synthetic_model_used"] is False
    assert result["provenance"]["persisted"] is False


@pytest.mark.parametrize("bad_affine", [
    np.zeros((4, 4)),
    np.array([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 0], [0, 0, 0, 1]], dtype=float),
])
def test_rejects_singular_or_invalid_affine(bad_affine):
    with pytest.raises(RealVolumeResearchError):
        _pair(affine=bad_affine)


def test_rejects_affine_mismatch():
    shifted = np.array([[0.5, 0, 0, -7], [0, 0.7, 0, -10], [0, 0, 1.2, -20], [0, 0, 0, 1]])
    with pytest.raises(RealVolumeResearchError, match="affine_mismatch"):
        _pair(mask_affine=shifted)


def test_rejects_dimension_mismatch_nonfinite_ct_and_nonbinary_mask():
    result = _pair()
    assert result["geometry"]["shape_ijk"] == [32, 32, 32]
    affine = np.eye(4)
    with pytest.raises(RealVolumeResearchError, match="matching_3d"):
        analyze_real_volume_arrays(np.zeros((4, 4, 4)), np.zeros((4, 4, 3)), affine, affine,
                                   ct_units="mm", mask_units="mm", ct_sha256=_digest("ct"), mask_file_sha256=_digest("mask"))
    ct = np.zeros((4, 4, 4)); ct[0, 0, 0] = np.nan
    with pytest.raises(RealVolumeResearchError, match="invalid_voxels"):
        analyze_real_volume_arrays(ct, np.zeros((4, 4, 4)), affine, affine,
                                   ct_units="mm", mask_units="mm", ct_sha256=_digest("ct"), mask_file_sha256=_digest("mask"))
    mask = np.zeros((4, 4, 4)); mask[1, 1, 1] = 2
    with pytest.raises(RealVolumeResearchError, match="binary"):
        analyze_real_volume_arrays(np.zeros((4, 4, 4)), mask, affine, affine,
                                   ct_units="mm", mask_units="mm", ct_sha256=_digest("ct"), mask_file_sha256=_digest("mask"))


def test_unknown_units_do_not_create_physical_coordinates_or_measurements():
    result = _pair(units="unknown", mask_units="unknown")
    assert result["geometry"]["voxel_spacing_mm"] is None
    assert result["geometry"]["affine_ras_mm"] is None
    assert result["centerline"]["status"] == "abstained"
    assert "physical_geometry_unavailable" in result["centerline"]["reasons"]
    assert result["measurements"]["minimum_lumen_diameter_mm"] is None


def test_rejects_known_incompatible_units_and_invalid_source_hash():
    with pytest.raises(RealVolumeResearchError, match="units_mismatch"):
        _pair(units="mm", mask_units="meter")
    affine = np.eye(4)
    with pytest.raises(RealVolumeResearchError, match="source_digest"):
        analyze_real_volume_arrays(np.zeros((4, 4, 4)), np.zeros((4, 4, 4)), affine, affine,
                                   ct_units="mm", mask_units="mm", ct_sha256="bad", mask_file_sha256=_digest("mask"))


def test_empty_mask_returns_explicit_abstention_and_false_flags():
    result = _pair()
    affine = np.eye(4)
    empty = np.zeros((8, 8, 8), dtype=np.uint8)
    value = analyze_real_volume_arrays(np.zeros_like(empty), empty, affine, affine,
                                       ct_units="mm", mask_units="mm", ct_sha256=_digest("ct"), mask_file_sha256=_digest("mask"))
    assert value["status"] == "abstained"
    assert value["centerline"]["reasons"] == ["empty_mask"]
    assert value["measurements"]["estimated_percentage_narrowing"] is None
    assert value["clinical_gate_authorized"] is False and value["training_release_authorized"] is False
