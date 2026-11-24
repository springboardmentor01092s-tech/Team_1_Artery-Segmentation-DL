"""Tiny synthetic arrays only; run --noconftest. Never database fixtures."""
from copy import deepcopy
from dataclasses import replace
import base64
import gzip
import hashlib
import json
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

from app.schemas.stenosis import AnalysisResult, Measurement, VolumeGeometry
from app.core.quantitative_gate import VALIDATED_GATES
from app.services.experimental_candidates import (
    CandidateInputError, ResearchParameters, extract_candidates, mask_identity,
)
from app.services.stenosis_geometry import geometry_fingerprint

RESULTS = []  # Collected by the external synthetic-only runner, never persisted in app.
PARAMETERS = ResearchParameters(.5, 8., 1., 4., 8., 4, .65, 2, 5.)


def fixture(kind="uniform"):
    spacing = np.array([.7, 1.1, 1.5]) if kind == "anisotropic" else np.ones(3)
    rotation = np.eye(3)
    if kind == "oblique":
        angle = .6
        rotation[:2, :2] = [[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]]
    affine = np.eye(4); affine[:3, :3] = rotation @ np.diag(spacing); affine[:3, 3] = [-11, 5, -7]
    i, j, k = np.indices((33, 33, 97))
    radius = np.full(97, 5.)
    truth = []
    if kind in {"focal", "anisotropic", "oblique"}: truth = [(34, 38)]
    if kind == "multiple": truth = [(28, 32), (62, 66)]
    for lo, hi in truth: radius[lo:hi + 1] = 2.5
    center_i = 4 if kind == "source-boundary" else 16
    mask = (((i - center_i) * spacing[0]) ** 2 + ((j - 16) * spacing[1]) ** 2 <= radius[k] ** 2).astype(np.uint8)
    if kind == "branching":
        for z in range(50, 73):
            mask |= (((i - (16 + (z - 50) * .4)) ** 2 + (j - 16) ** 2 + (k - z) ** 2) <= 3 ** 2).astype(np.uint8)
    if kind == "disconnected": mask[2:4, 2:4, 20:23] = 1
    if kind == "empty": mask[:] = 0
    if kind == "pocket": mask[18, 16, :] = 0  # Internal pocket, not the centerline.
    geometry = VolumeGeometry(shape=mask.shape, array_axis_order="nifti_i_j_k", world_convention="RAS", world_unit="mm", affine=affine.tolist())
    source = {"source_sha256": "a" * 64, "mask_sha256": mask_identity(mask, 1),
              "geometry_fingerprint": geometry_fingerprint(geometry, "a" * 64), "mask_role": "supplied_segmentation",
              "parent_segmentation_result_id": None, "target_label": 1}
    z = np.arange(4., 93., 1 / spacing[2]) if kind != "short" else np.arange(44., 51.)
    branch = {"branch_id": "main", "ordered": True, "points_ijk": np.column_stack([z * 0 + center_i, z * 0 + 16, z]).tolist(),
              "junctions_s_mm": [46.] if kind == "branching" else [], "mask_sha256": source["mask_sha256"],
              "geometry_fingerprint": source["geometry_fingerprint"]}
    return mask, geometry, spacing, source, [branch], truth


@pytest.mark.parametrize("kind", ["uniform", "focal", "multiple", "branching", "disconnected", "anisotropic", "oblique", "short", "empty", "pocket", "source-boundary"])
def test_synthetic_behavior(kind):
    mask, geometry, spacing, source, branches, truth = fixture(kind)
    before = mask.copy(), deepcopy(branches), dict(source)
    result = extract_candidates(mask, geometry, spacing, source, branches, PARAMETERS)
    matched = set(); false_positive = 0
    inverse = np.linalg.inv(np.asarray(geometry.affine))
    for candidate in result["candidates"]:
        point = inverse[:3, :3] @ candidate["world_ras_mm"] + inverse[:3, 3]
        assert np.allclose(point, candidate["sample_ijk"])
        matches = [n for n, (lo, hi) in enumerate(truth) if lo - 1 <= point[2] <= hi + 1 and n not in matched]
        if matches: matched.add(matches[0])
        else: false_positive += 1
    abstentions = sum(b["abstained_sections"] for b in result["branches"])
    RESULTS.append({"fixture": kind, "truth_regions": len(truth), "candidates": len(result["candidates"]),
                    "true_positive": len(matched), "false_positive": false_positive, "false_negative": len(truth) - len(matched),
                    "total_sections": sum(len(b["sections"]) for b in result["branches"]),
                    "evaluable_sections": sum(b["evaluable_sections"] for b in result["branches"]),
                    "abstained_sections": abstentions, "global_abstention": result["status"] == "abstained",
                    "status": result["status"], "reason": result["reason"]})
    assert len(matched) == len(truth) and false_positive == 0
    if kind in {"disconnected", "empty", "short", "pocket", "source-boundary"}: assert result["status"] == "abstained"
    if kind == "branching":
        excluded = [r for r in result["branches"][0]["sections"] if abs(r["s_mm"] - 46) <= 5]
        assert excluded and all(r["reason"] == "junction_exclusion" for r in excluded)
    assert np.array_equal(mask, before[0]) and branches == before[1] and source == before[2]
    assert result["measurement_status"] == "measurement_unavailable_no_validated_gate"
    encoded = json.dumps(result, allow_nan=False)
    assert '"severity"' not in encoded and '"percentage_narrowing"' not in encoded and '"confidence"' not in encoded


@pytest.mark.parametrize("defect", ["singular", "shear", "spacing", "missing_spacing", "outside_mask", "unordered", "source", "mask", "branch_source", "label", "fractional"])
def test_invalid_inputs_fail_explicitly(defect):
    mask, geometry, spacing, source, branches, _ = fixture()
    g = geometry.model_dump(mode="json")
    if defect == "singular": g["affine"][0] = [0, 0, 0, 0]
    if defect == "shear": g["affine"][0][1] = .1
    if defect == "spacing": spacing = [2, 1, 1]
    if defect == "missing_spacing": spacing = None
    if defect == "outside_mask": branches[0]["points_ijk"][15][0] = 25
    if defect == "unordered": branches[0]["points_ijk"][10:12] = branches[0]["points_ijk"][10:12][::-1]
    if defect == "source": source["source_sha256"] = "b" * 64
    if defect == "mask": mask[16, 16, 10] = 0
    if defect == "branch_source": branches[0]["mask_sha256"] = "c" * 64
    if defect == "label": source["target_label"] = 0
    if defect == "fractional": mask = mask.astype(float); mask[16, 16, 10] = .2
    with pytest.raises(ValueError) as failure:
        extract_candidates(mask, g, spacing, source, branches, PARAMETERS)
    RESULTS.append({"fixture": "reject_" + defect, "truth_regions": None, "candidates": None,
                    "true_positive": None, "false_positive": None, "false_negative": None,
                    "total_sections": None, "evaluable_sections": None, "abstained_sections": None,
                    "global_abstention": None, "status": "rejected", "reason": str(failure.value).splitlines()[0]})


def test_multiple_label_identity_includes_unselected_categories():
    mask, geometry, spacing, source, branches, _ = fixture()
    mask[0, 0, 0] = 2
    assert mask_identity(mask, 1) != source["mask_sha256"]
    source["mask_sha256"] = mask_identity(mask, 1); branches[0]["mask_sha256"] = source["mask_sha256"]
    assert extract_candidates(mask, geometry, spacing, source, branches, PARAMETERS)["candidates"] == []


def test_resource_limits_precede_plane_allocation():
    args = fixture()[:5]
    with pytest.raises(CandidateInputError, match="plane_resource_limit"):
        extract_candidates(*args, replace(PARAMETERS, plane_radius_mm=1000.))


def test_plane_boundary_abstains_without_automatic_expansion():
    result = extract_candidates(*fixture()[:5], replace(PARAMETERS, plane_radius_mm=2.))
    assert not result["candidates"] and result["status"] == "abstained"
    assert any(r["reason"] == "plane_fov_limited" for r in result["branches"][0]["sections"])


def test_connected_3d_mask_with_two_plane_components_is_not_silently_selected():
    mask, geometry, spacing, source, branches, _ = fixture()
    i, j, _ = np.indices(mask.shape)
    mask = (((i - 16)**2 + (j - 16)**2 <= 2**2) | ((i - 21)**2 + (j - 16)**2 <= 1.5**2)).astype(np.uint8)
    mask[16:22, 16, 80] = 1  # One global component, two separate section islands.
    source["mask_sha256"] = mask_identity(mask, 1); branches[0]["mask_sha256"] = source["mask_sha256"]
    result = extract_candidates(mask, geometry, spacing, source, branches, PARAMETERS)
    rows = result["branches"][0]["sections"]
    assert result["status"] == "abstained" and not result["candidates"]
    assert any(r["reason"] == "ambiguous_disconnected_plane" and r["plane_components"] == 2 for r in rows)


def test_supplied_intersecting_branches_are_excluded_from_reference():
    mask, geometry, spacing, source, branches, _ = fixture("branching")
    side = deepcopy(branches[0]); side["branch_id"] = "side"; side["junctions_s_mm"] = [0.]
    side["points_ijk"] = [[16 + (z - 50) * .4, 16, z] for z in range(50, 73)]
    branches.append(side)
    result = extract_candidates(mask, geometry, spacing, source, branches, PARAMETERS)
    assert not result["candidates"]
    assert all(any(r["reason"] == "junction_exclusion" for r in b["sections"]) for b in result["branches"])


def test_candidate_is_not_a_trusted_result_or_gate():
    result = extract_candidates(*fixture("focal")[:5], PARAMETERS)
    assert result["candidates"] and not VALIDATED_GATES
    with pytest.raises(ValueError): AnalysisResult.model_validate(result)
    with pytest.raises(ValueError):
        Measurement(value=0, unit="mm", unavailable_reason=None, method_id="experimental-mask-profile", method_version="0.1.0",
                    validation_gate={"gate_id": "candidate-001", "validated": True})


def test_reference_annotation_never_becomes_model_prediction():
    mask, geometry, spacing, source, branches, _ = fixture("focal")
    source["mask_role"] = "reference_annotation"
    result = extract_candidates(mask, geometry, spacing, source, branches, PARAMETERS)
    assert result["source"]["mask_role"] == "reference_annotation"
    source["parent_segmentation_result_id"] = "00000000-0000-4000-8000-000000000001"
    with pytest.raises(CandidateInputError, match="annotation_is_not_a_prediction"):
        extract_candidates(mask, geometry, spacing, source, branches, PARAMETERS)


def test_substep_branch_refuses_before_numpy_gradient(monkeypatch):
    args = list(fixture()[:5])
    args[4][0]["points_ijk"] = [[16, 16, 44], [16, 16, 44.1], [16, 16, 44.2]]
    before = deepcopy(args[4])
    def forbidden(*_args, **_kwargs):
        raise AssertionError("An insufficient branch must not reach np.gradient")
    monkeypatch.setattr(np, "gradient", forbidden)
    with pytest.raises(CandidateInputError, match="insufficient_branch_samples"):
        extract_candidates(*args, PARAMETERS)
    assert args[4] == before


def test_two_sample_branch_abstains_with_source_and_geometry():
    args = list(fixture()[:5])
    args[4][0]["points_ijk"] = [[16, 16, 44], [16, 16, 44.6], [16, 16, 45.2]]
    result = extract_candidates(*args, PARAMETERS)
    assert result["status"] == "abstained" and not result["candidates"]
    assert result["reason"] == "no_evaluable_reference_support"
    assert result["source"] == args[3] and result["geometry"] == args[1].model_dump(mode="json")
    assert len(result["branches"][0]["sections"]) == 2


def generate_frontend_fixture(layout):
    """Deterministic synthetic bundles, not patient data or application seeds.

    Called explicitly when preparing fixtures; tests below re-extract the stored
    categorical bytes instead of trusting a hand-authored positive preview.
    """
    if layout not in {"flipped", "permuted"}: raise ValueError("Unknown synthetic layout")
    mask, _, spacing, _, branches, _ = fixture("focal")
    affine = ([[-1, 0, 0, 16], [0, 1, 0, -16], [0, 0, 1, -7], [0, 0, 0, 1]] if layout == "flipped"
              else [[0, 0, -1, 48], [-1, 0, 0, 16], [0, 1, 0, -16], [0, 0, 0, 1]])
    geometry = VolumeGeometry(shape=mask.shape, affine=affine, array_axis_order="nifti_i_j_k", world_convention="RAS", world_unit="mm")
    ct = nib.Nifti1Image(np.zeros(mask.shape, dtype=np.int16), affine)
    image = nib.Nifti1Image(mask, affine)
    for volume in (ct, image): volume.header.set_xyzt_units("mm")
    ct_bytes, mask_bytes = (gzip.compress(v.to_bytes(), mtime=0) for v in (ct, image))
    source_sha = hashlib.sha256(ct_bytes).hexdigest()
    source = {"source_sha256": source_sha, "mask_sha256": mask_identity(mask, 1),
              "geometry_fingerprint": geometry_fingerprint(geometry, source_sha), "mask_role": "model_prediction",
              "parent_segmentation_result_id": "12345678-1234-4567-890a-123456789abc", "target_label": 1}
    branches[0].update(mask_sha256=source["mask_sha256"], geometry_fingerprint=source["geometry_fingerprint"])
    no_candidate = deepcopy(branches); no_candidate[0]["points_ijk"] = [p for p in branches[0]["points_ijk"] if p[2] <= 29]
    abstained = deepcopy(branches); abstained[0]["points_ijk"] = [[16., 16., float(z)] for z in range(44, 51)]
    inputs = {"preview": branches, "no_candidate_preview": no_candidate, "abstained_preview": abstained}
    return {"description": "SYNTHETIC BACKEND-GENERATED FIXTURE ONLY; NOT PATIENT DATA OR AN APPLICATION RECORD",
            "layout": layout, "ct_gzip_base64": base64.b64encode(ct_bytes).decode(),
            "mask_gzip_base64": base64.b64encode(mask_bytes).decode(), "input_branches": inputs,
            **{key: extract_candidates(mask, geometry, spacing, source, value, PARAMETERS) for key, value in inputs.items()}}


@pytest.mark.parametrize("layout", ["flipped", "permuted"])
def test_serialized_frontend_fixtures_are_actual_backend_outputs(layout):
    path = Path(__file__).resolve().parents[2] / "frontend-react" / "tests" / "fixtures" / f"experimental-preview-{layout}.json"
    bundle = json.loads(path.read_text(encoding="utf-8"))
    raw_ct = base64.b64decode(bundle["ct_gzip_base64"])
    image = nib.Nifti1Image.from_bytes(gzip.decompress(base64.b64decode(bundle["mask_gzip_base64"])))
    assert image.header.get_xyzt_units()[0] == "mm"
    mask = np.asanyarray(image.dataobj)
    g = VolumeGeometry(shape=mask.shape, affine=image.affine.tolist(), array_axis_order="nifti_i_j_k", world_convention="RAS", world_unit="mm")
    for key in ("preview", "no_candidate_preview", "abstained_preview"):
        actual = bundle[key]
        assert hashlib.sha256(raw_ct).hexdigest() == actual["source"]["source_sha256"]
        rebuilt = extract_candidates(mask, g, image.header.get_zooms()[:3], actual["source"], bundle["input_branches"][key], ResearchParameters(**actual["parameters"]))
        assert rebuilt == actual
