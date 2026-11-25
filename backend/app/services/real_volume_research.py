"""Bounded, non-persistent real-volume QC and experimental topology analysis.

This path deliberately does not call the synthetic CNN. Current ImageCAS
annotations are artery-segmentation masks with unresolved physical units and
unverified lumen semantics, so lesion candidates and lumen measurements
remain unavailable even when a digital skeleton can be extracted.
"""
from __future__ import annotations

import hashlib
from typing import Any

import nibabel as nib
import numpy as np
from scipy.ndimage import label

from app.schemas.stenosis import VolumeGeometry
from app.services.experimental_branches import extract_branch_graph
from app.services.experimental_candidates import mask_identity
from app.services.stenosis_geometry import geometry_fingerprint

MAX_REAL_VOXELS = 67_108_864
MAX_AUTOMATIC_BRANCH_VOXELS = 4_000_000
NOTICE = (
    "REAL-VOLUME RESEARCH QC ONLY — not a diagnosis. The supplied mask's "
    "lumen semantics are unverified; stenosis candidates and lumen measurements "
    "are unavailable. No synthetic model was run."
)
_UNIT_TO_MM = {"mm": 1.0, "meter": 1000.0, "micron": 0.001}


class RealVolumeResearchError(ValueError):
    """Safe, input-independent refusal for unsupported volume pairs."""


def file_sha256(path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(block_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _valid_affine(affine: Any) -> np.ndarray:
    value = np.asarray(affine, dtype=np.float64)
    if value.shape != (4, 4) or not np.isfinite(value).all():
        raise RealVolumeResearchError("invalid_affine")
    if not np.allclose(value[3], (0, 0, 0, 1), atol=1e-8, rtol=0):
        raise RealVolumeResearchError("invalid_affine")
    scaled = value[:3, :3] / np.maximum(np.max(np.abs(value[:3, :3]), axis=0), 1e-300)
    if abs(float(np.linalg.det(scaled))) < 1e-8:
        raise RealVolumeResearchError("singular_affine")
    return value


def _unit_factor(units: str | None) -> float | None:
    if not units or units == "unknown":
        return None
    return _UNIT_TO_MM.get(str(units).lower())


def analyze_real_volume_arrays(
    ct: np.ndarray,
    mask: np.ndarray,
    ct_affine: Any,
    mask_affine: Any,
    *,
    ct_units: str,
    mask_units: str,
    ct_sha256: str,
    mask_file_sha256: str,
) -> dict[str, Any]:
    """Validate an original-grid CT/mask pair and report nonclinical evidence.

    Candidate extraction is refused because this runtime has no independently
    authorized source registry that can attest a supplied mask is a lumen mask.
    """
    ct = np.asarray(ct)
    mask_array = np.asarray(mask)
    if ct.ndim != 3 or mask_array.ndim != 3 or ct.shape != mask_array.shape:
        raise RealVolumeResearchError("ct_and_mask_must_be_matching_3d_arrays")
    if any(size < 2 or size > 1024 for size in ct.shape) or ct.size > MAX_REAL_VOXELS:
        raise RealVolumeResearchError("volume_exceeds_research_resource_limit")
    if ct.dtype.kind not in "uif" or not np.isfinite(ct).all():
        raise RealVolumeResearchError("ct_contains_invalid_voxels")
    if mask_array.dtype.kind not in "buif" or not np.isfinite(mask_array).all():
        raise RealVolumeResearchError("mask_contains_invalid_voxels")
    if not np.isin(mask_array, (0, 1)).all():
        raise RealVolumeResearchError("mask_must_be_binary_0_or_1")
    image_affine = _valid_affine(ct_affine)
    annotation_affine = _valid_affine(mask_affine)
    if not np.allclose(image_affine, annotation_affine, atol=1e-4, rtol=1e-6):
        raise RealVolumeResearchError("ct_mask_affine_mismatch")
    if ct_units not in {"mm", "meter", "micron", "unknown", "None"}:
        raise RealVolumeResearchError("unsupported_ct_spatial_units")
    if mask_units not in {"mm", "meter", "micron", "unknown", "None"}:
        raise RealVolumeResearchError("unsupported_mask_spatial_units")
    if mask_units not in {"unknown", "None", ct_units}:
        raise RealVolumeResearchError("ct_mask_spatial_units_mismatch")
    for digest in (ct_sha256, mask_file_sha256):
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise RealVolumeResearchError("invalid_source_digest")

    factor = _unit_factor(ct_units)
    mm_affine = image_affine.copy()
    if factor is not None:
        mm_affine[:3, :] *= factor
    spacing_native = np.linalg.norm(image_affine[:3, :3], axis=0)
    spacing_mm = np.linalg.norm(mm_affine[:3, :3], axis=0) if factor is not None else None
    geometry_fp = None
    physical_geometry = None
    if factor is not None:
        physical_geometry = VolumeGeometry(
            shape=tuple(int(n) for n in ct.shape), array_axis_order="nifti_i_j_k",
            world_convention="RAS", world_unit="mm",
            affine=tuple(tuple(float(v) for v in row) for row in mm_affine),
        )
        geometry_fp = geometry_fingerprint(physical_geometry, ct_sha256)
    binary = mask_array.astype(bool, copy=False)
    components, component_count = label(binary, structure=np.ones((3, 3, 3), dtype=np.uint8))
    sizes = np.bincount(components.ravel()) if component_count else np.array([0])
    component_voxels = sorted((int(value) for value in sizes[1:]), reverse=True)
    foreground = int(np.count_nonzero(binary))
    orientation = [str(axis) for axis in nib.aff2axcodes(image_affine)]

    graph: dict[str, Any] = {
        "status": "abstained", "reasons": ["physical_geometry_unavailable"] if factor is None else [],
        "branches": [], "diagnostics": {"input_components_26": int(component_count)},
        "warning": "Digital skeleton topology is not a validated anatomical centerline.",
    }
    if foreground and factor is not None and binary.size <= MAX_AUTOMATIC_BRANCH_VOXELS:
        geometry = physical_geometry
        mask_hash = mask_identity(binary.astype(np.uint8), 1)
        source = {
            "source_sha256": ct_sha256, "mask_sha256": mask_hash,
            "geometry_fingerprint": geometry_fingerprint(geometry, ct_sha256),
            "mask_role": "supplied_segmentation", "parent_segmentation_result_id": None,
            "target_label": 1,
        }
        try:
            graph = extract_branch_graph(binary, geometry, tuple(float(x) for x in spacing_mm), source)
        except (ValueError, RuntimeError, MemoryError, OverflowError):
            graph = {"status": "abstained", "reasons": ["centerline_extraction_failed_safely"],
                     "branches": [], "diagnostics": {"input_components_26": int(component_count)},
                     "warning": "Digital skeleton topology is not a validated anatomical centerline."}
    elif foreground and factor is not None:
        graph["reasons"] = ["automatic_branch_graph_resource_limit"]
    elif not foreground:
        graph["reasons"] = ["empty_mask"]

    status = "profile_only" if foreground else "abstained"
    return {
        "schema_version": "real-volume-research/0.1", "status": status, "notice": NOTICE,
        "provenance": {"ct_sha256": ct_sha256, "mask_file_sha256": mask_file_sha256,
                       "persisted": False, "synthetic_model_used": False},
        "geometry": {"shape_ijk": [int(n) for n in ct.shape], "orientation": orientation,
                     "ct_spatial_units": ct_units, "mask_spatial_units": mask_units,
                     "voxel_spacing_native": [float(v) for v in spacing_native],
                     "voxel_spacing_mm": [float(v) for v in spacing_mm] if spacing_mm is not None else None,
                     "affine_ras_mm": mm_affine.tolist() if factor is not None else None,
                     "geometry_fingerprint": geometry_fp,
                     "geometry_source": "CT NIfTI affine; mask affine equality checked"},
        "segmentation": {"semantics": "supplied_coronary_artery_segmentation_unverified_lumen",
                         "foreground_voxels": foreground, "component_count_26": int(component_count),
                         "component_voxel_counts_descending": component_voxels[:128],
                         "component_list_truncated": len(component_voxels) > 128},
        "centerline": graph,
        "candidates": [], "candidate_status": "unavailable_mask_semantics_unverified",
        "measurements": {"reference_lumen_area_mm2": None, "minimum_lumen_area_mm2": None,
                         "reference_lumen_diameter_mm": None, "minimum_lumen_diameter_mm": None,
                         "estimated_percentage_narrowing": None, "provisional_severity": None,
                         "availability": "unavailable_lumen_semantics_unverified",
                         "reason": "The source mask is not independently attested as a lumen contour."},
        "clinical_validation": False, "clinical_gate_authorized": False,
        "training_release_authorized": False,
    }


def analyze_nifti_pair(ct_path, mask_path) -> dict[str, Any]:
    """Decode an already bounded NIfTI pair without retaining or persisting it."""
    # Materialize within the validated voxel cap so no mmap/file handle survives
    # response construction; Windows can then reliably remove both temp files.
    ct_image = nib.load(str(ct_path), mmap=False)
    mask_image = nib.load(str(mask_path), mmap=False)
    if len(ct_image.shape) != 3 or len(mask_image.shape) != 3:
        raise RealVolumeResearchError("only_3d_nifti_volumes_are_supported")
    if ct_image.shape != mask_image.shape:
        raise RealVolumeResearchError("ct_and_mask_dimensions_mismatch")
    ct_units = ct_image.header.get_xyzt_units()[0] or "unknown"
    mask_units = mask_image.header.get_xyzt_units()[0] or "unknown"
    try:
        # Do not use get_fdata(): preserve integer masks and avoid an implicit float64 copy.
        ct = np.asanyarray(ct_image.dataobj)
        mask = np.asanyarray(mask_image.dataobj)
    except (OSError, ValueError, MemoryError) as exc:
        raise RealVolumeResearchError("nifti_voxel_payload_unreadable") from exc
    return analyze_real_volume_arrays(
        ct, mask, ct_image.affine, mask_image.affine, ct_units=ct_units, mask_units=mask_units,
        ct_sha256=file_sha256(ct_path), mask_file_sha256=file_sha256(mask_path),
    )
