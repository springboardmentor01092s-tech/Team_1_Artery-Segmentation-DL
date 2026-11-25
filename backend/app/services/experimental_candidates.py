"""Bounded, supplied-array research preview. No routes, IO, DB or runtime registration.

This categorical-mask profile is independent of the unmerged SDF operator. All
parameters are unvalidated research choices, not an operating/measurement gate.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
import re
import struct
from uuid import UUID

import numpy as np
from scipy.ndimage import label

from app.schemas.stenosis import VolumeGeometry
from app.services.stenosis_geometry import geometry_fingerprint

METHOD = "experimental-mask-profile"
VERSION = "0.1.0"
NOTICE = "EXPERIMENTAL — NOT A DIAGNOSIS"
MASK_PREFIX = b"vascuai-experimental-mask-v1\0"
MAX_VOXELS = 4_000_000
MAX_SECTIONS = 2048
MAX_PLANE_NODES = 8_000_000
MAX_POINTS = 1024
MAX_BRANCHES = 8
MAX_OUTPUT_BYTES = 2 * 1024 * 1024


class CandidateInputError(ValueError):
    """No preview should be interpreted after this explicit refusal."""


@dataclass(frozen=True)
class ResearchParameters:
    plane_pitch_mm: float
    plane_radius_mm: float
    sample_step_mm: float
    reference_inner_mm: float
    reference_outer_mm: float
    minimum_reference_samples_each_side: int
    area_ratio_trigger: float
    minimum_candidate_sections: int
    junction_exclusion_mm: float

    def validate(self):
        # Validate scalar types before asdict() could deepcopy an invalid array.
        numbers = vars(self)
        if any(isinstance(x, (bool,np.bool_)) or not isinstance(x,(int,float,np.integer,np.floating)) or not np.isfinite(x) or x <= 0 for x in numbers.values()):
            raise CandidateInputError("invalid_research_parameters")
        if not (0 < self.area_ratio_trigger < 1 and self.reference_inner_mm < self.reference_outer_mm):
            raise CandidateInputError("invalid_reference_or_sensitivity")
        for value in (self.minimum_reference_samples_each_side, self.minimum_candidate_sections):
            if not isinstance(value, int) or value < 2:
                raise CandidateInputError("invalid_minimum_sample_count")
        ratio=self.plane_radius_mm/self.plane_pitch_mm
        pixel_area=self.plane_pitch_mm*self.plane_pitch_mm
        if not np.isfinite(ratio) or ratio>128 or not np.isfinite(pixel_area) or pixel_area<=0:
            raise CandidateInputError('plane_resource_limit')
        n = int(np.ceil(ratio))
        if n < 1 or 2 * n + 1 > 257:
            raise CandidateInputError("plane_resource_limit")
        return n


def _categorical(mask, target_label):
    a = np.asarray(mask)
    if a.ndim != 3 or any(n < 2 for n in a.shape) or a.size > MAX_VOXELS:
        raise CandidateInputError("mask_dimensions_or_resource_limit")
    if isinstance(target_label, bool) or not isinstance(target_label, int) or not 0 < target_label <= 0xffffffff:
        raise CandidateInputError("explicit_positive_target_label_required")
    if a.dtype.kind not in "buif" or not np.isfinite(a).all() or np.any(a < 0) or np.any(a > 0xffffffff) or np.any(a != np.floor(a)):
        raise CandidateInputError("mask_must_be_categorical")
    return a


def mask_identity(mask, target_label):
    """Canonical full categorical array, C-order uint32 LE; not a file SHA-256."""
    a = _categorical(mask, target_label)
    digest = hashlib.sha256(MASK_PREFIX + struct.pack("<4I", *a.shape, target_label))
    digest.update(np.asarray(a, dtype="<u4", order="C").tobytes(order="C"))
    return digest.hexdigest()


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _geometry(mask, geometry, spacing):
    g = VolumeGeometry.model_validate(geometry)
    a = np.asarray(g.affine, dtype=float)
    lengths = np.linalg.norm(a[:3, :3], axis=0)
    if tuple(mask.shape) != g.shape or spacing is None:
        raise CandidateInputError("shape_or_missing_spacing")
    s = np.asarray(spacing, dtype=float)
    if s.shape != (3,) or not np.isfinite(s).all() or np.any(s <= 0) or not np.allclose(s, lengths, rtol=1e-6, atol=1e-6):
        raise CandidateInputError("spacing_affine_mismatch")
    axes = a[:3, :3] / lengths
    if not np.allclose(axes.T @ axes, np.eye(3), atol=1e-6):
        raise CandidateInputError("sheared_geometry_unsupported")
    return g, a, np.linalg.inv(a)


def _branch(branch, source, g, a, lumen, params):
    if not isinstance(branch, dict) or set(branch) != {"branch_id", "ordered", "points_ijk", "junctions_s_mm", "mask_sha256", "geometry_fingerprint"}:
        raise CandidateInputError("explicit_ordered_branch_contract_required")
    if branch["ordered"] is not True or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", str(branch["branch_id"])):
        raise CandidateInputError("invalid_branch_identity_or_order")
    if any(branch[k] != source[k] for k in ("mask_sha256", "geometry_fingerprint")):
        raise CandidateInputError("branch_source_mismatch")
    ijk = np.asarray(branch["points_ijk"], dtype=float)
    if ijk.ndim != 2 or ijk.shape[1] != 3 or not 3 <= len(ijk) <= MAX_POINTS or not np.isfinite(ijk).all():
        raise CandidateInputError("invalid_ordered_points")
    if np.any(ijk < 0) or np.any(ijk > np.asarray(g.shape) - 1) or len(np.unique(ijk, axis=0)) != len(ijk):
        raise CandidateInputError("out_of_bounds_or_repeated_centerline")
    world = ijk @ a[:3, :3].T + a[:3, 3]
    delta = np.diff(world, axis=0)
    lengths = np.linalg.norm(delta, axis=1)
    if np.any(lengths < 1e-6) or np.any(lengths > 2 * params.sample_step_mm):
        raise CandidateInputError("centerline_gap_or_duplicate")
    directions = delta / lengths[:, None]
    if np.any(np.sum(directions[1:] * directions[:-1], axis=1) <= 0.5):
        raise CandidateInputError("unordered_or_sharply_turning_centerline")
    arcs = np.r_[0., np.cumsum(lengths)]
    junctions = np.asarray(branch["junctions_s_mm"], dtype=float)
    if junctions.ndim != 1 or not np.isfinite(junctions).all() or np.any(junctions < 0) or np.any(junctions > arcs[-1]):
        raise CandidateInputError("invalid_junction_positions")
    dense_step = min(params.sample_step_mm, min(np.linalg.norm(a[:3, :3], axis=0))) / 2
    if arcs[-1] / params.sample_step_mm > 511 or arcs[-1] / dense_step > 16384:
        raise CandidateInputError("branch_section_resource_limit")
    # Check every connecting segment, not only the supplied vertices.
    dense = np.arange(0, arcs[-1], dense_step)
    path = np.column_stack([np.interp(dense, arcs, ijk[:, axis]) for axis in range(3)])
    indices = np.floor(path + 0.5).astype(int)
    if not lumen[tuple(indices.T)].all() or not lumen[tuple(np.floor(ijk + 0.5).astype(int).T)].all():
        raise CandidateInputError("centerline_outside_target_mask")
    samples = np.arange(0, arcs[-1] + 1e-8, params.sample_step_mm)
    if len(samples) > 512:
        raise CandidateInputError("branch_section_resource_limit")
    if len(samples) < 2:
        raise CandidateInputError("insufficient_branch_samples")
    points = np.column_stack([np.interp(samples, arcs, world[:, axis]) for axis in range(3)])
    tangents = np.gradient(points, axis=0)
    tangents /= np.linalg.norm(tangents, axis=1)[:, None]
    return samples, points, tangents, junctions


def _plane(lumen, inverse, center, tangent, grid):
    helper = np.eye(3)[np.argmin(np.abs(tangent))]
    u = np.cross(tangent, helper); u /= np.linalg.norm(u)
    v = np.cross(tangent, u)
    xyz = center + grid[..., :1] * u + grid[..., 1:] * v
    ijk = xyz @ inverse[:3, :3].T + inverse[:3, 3]
    if np.any(ijk < -1e-7) or np.any(ijk > np.asarray(lumen.shape) - 1 + 1e-7):
        return None, "source_volume_boundary", 0
    indices = np.floor(np.clip(ijk, 0, np.asarray(lumen.shape) - 1) + 0.5).astype(int)
    plane = lumen[tuple(indices.reshape(-1, 3).T)].reshape(grid.shape[:2])
    components, count = label(plane, structure=np.ones((3, 3), dtype=int))
    n = plane.shape[0] // 2
    if not plane[n, n]: return None, "background_center", count
    if np.any(plane[0]) or np.any(plane[-1]) or np.any(plane[:, 0]) or np.any(plane[:, -1]):
        return None, "plane_fov_limited", count
    if count != 1: return None, "ambiguous_disconnected_plane", count
    background, _ = label(~plane)  # dual 4-connectivity; detect holes, never fill.
    border = np.unique(np.r_[background[0], background[-1], background[:, 0], background[:, -1], 0])
    if np.any(~np.isin(background, border)): return None, "internal_pocket", count
    return int(np.count_nonzero(plane)), None, count


def extract_candidates(mask, geometry, spacing, source, branches, parameters):
    """Pure preview from explicitly supplied arrays/ordered branches; never infer CT.

    Source SHA is a caller-supplied CT binding, not proof that this function read a
    CT. The actual full categorical array hash and geometry binding are checked.
    """
    if not isinstance(parameters, ResearchParameters): raise CandidateInputError("explicit_research_parameters_required")
    n = parameters.validate()
    _validate_source(source)
    mask = _categorical(mask, source["target_label"])
    g, affine, inverse = _geometry(mask, geometry, spacing)
    if mask_identity(mask, source["target_label"]) != source["mask_sha256"] or geometry_fingerprint(g, source["source_sha256"]) != source["geometry_fingerprint"]:
        raise CandidateInputError("source_identity_mismatch")
    lumen = mask == source["target_label"]
    components, count = label(lumen)
    del components
    return _sample_profile(lumen, g, affine, inverse, source, branches, parameters, n, count)


def _validate_source(source):
    if not isinstance(source, dict) or set(source) != {"source_sha256", "mask_sha256", "geometry_fingerprint", "mask_role", "parent_segmentation_result_id", "target_label"}:
        raise CandidateInputError("explicit_source_binding_required")
    for key in ("source_sha256", "mask_sha256", "geometry_fingerprint"):
        if not isinstance(source[key], str) or not re.fullmatch("[a-f0-9]{64}", source[key]): raise CandidateInputError("invalid_source_digest")
    if source["mask_role"] not in {"model_prediction", "reference_annotation", "supplied_segmentation"}:
        raise CandidateInputError("explicit_mask_role_required")
    parent = source["parent_segmentation_result_id"]
    if source["mask_role"] == "model_prediction":
        try:
            if not isinstance(parent, str) or str(UUID(parent)) != parent: raise ValueError()
        except ValueError:
            raise CandidateInputError("prediction_parent_required") from None
    if source["mask_role"] != "model_prediction" and parent is not None: raise CandidateInputError("annotation_is_not_a_prediction")


def _sample_profile(lumen, g, affine, inverse, source, branches, parameters, n, count):
    """Shared plane/reference operator; storage and connectivity are validated first."""
    if not isinstance(branches, list) or not 1 <= len(branches) <= MAX_BRANCHES:
        raise CandidateInputError("branch_count_limit")
    if any(not isinstance(b,dict) or not isinstance(b.get('branch_id'),str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',b['branch_id']) for b in branches):
        raise CandidateInputError('invalid_branch_identity_or_order')
    if len({b.get("branch_id") for b in branches if isinstance(b, dict)}) != len(branches): raise CandidateInputError("duplicate_branch_identity")
    result = {"schema_version": "experimental-candidates/1.0", "algorithm": {"id": METHOD, "version": VERSION},
              "notice": NOTICE, "measurement_status": "measurement_unavailable_no_validated_gate",
              "source": dict(source), "geometry": g.model_dump(mode="json"),
              "parameters": asdict(parameters), "parameter_status": "unvalidated_research_parameters",
              "parameters_sha256": _digest(asdict(parameters)), "branch_geometry_sha256": _digest(branches),
              "candidates": [], "branches": [], "status": "abstained", "reason": None}
    if count != 1:
        result["reason"] = "empty_mask" if count == 0 else "disconnected_source_mask"
        return result
    plans = [_branch(b, source, g, affine, lumen, parameters) for b in branches]
    total = sum(len(p[0]) for p in plans)
    if total > MAX_SECTIONS or total * (2 * n + 1) ** 2 > MAX_PLANE_NODES:
        raise CandidateInputError("sampling_resource_limit")
    axis = np.arange(-n, n + 1) * parameters.plane_pitch_mm
    grid = np.stack(np.meshgrid(axis, axis, indexing="ij"), axis=-1)
    for index, (branch, plan) in enumerate(zip(branches, plans)):
        arcs, points, tangents, junctions = plan
        # Other supplied branches touching this path create additional exclusions;
        # never use junction-inflated sections as reference support.
        near_junction = np.zeros(len(arcs), dtype=bool)
        for j, other in enumerate(plans):
            if j != index:
                near_junction |= np.min(np.linalg.norm(points[:, None] - other[1][None, :], axis=2), axis=1) <= parameters.junction_exclusion_mm
        rows = []
        for k, (s, point, tangent) in enumerate(zip(arcs, points, tangents)):
            excluded = (s < parameters.reference_inner_mm or arcs[-1] - s < parameters.reference_inner_mm)
            junction = near_junction[k] or np.any(np.abs(junctions - s) <= parameters.junction_exclusion_mm)
            reason = "junction_exclusion" if junction else "endpoint_exclusion" if excluded else None
            pixels, rejection, plane_components = (None, reason, None) if reason else _plane(lumen, inverse, point, tangent, grid)
            ijk = inverse[:3, :3] @ point + inverse[:3, 3]
            rows.append({"s_mm": float(s), "sample_ijk": ijk.tolist(), "world_ras_mm": point.tolist(),
                         "pixel_count": pixels, "diagnostic_area_mm2": pixels * parameters.plane_pitch_mm**2 if pixels else None,
                         "plane_components": plane_components, "status": "abstained" if rejection else "sampled",
                         "reason": rejection, "reference_samples_each_side": [0, 0]})
        flags = []
        for k, row in enumerate(rows):
            if row["status"] != "sampled": continue
            offsets = arcs - arcs[k]
            left = np.flatnonzero((offsets <= -parameters.reference_inner_mm) & (offsets >= -parameters.reference_outer_mm))
            right = np.flatnonzero((offsets >= parameters.reference_inner_mm) & (offsets <= parameters.reference_outer_mm))
            sides = (left, right)
            row["reference_samples_each_side"] = [int(sum(rows[j]["diagnostic_area_mm2"] is not None for j in side)) for side in sides]
            if any(len(side) < parameters.minimum_reference_samples_each_side or any(rows[j]["diagnostic_area_mm2"] is None for j in side) for side in sides):
                row.update(status="abstained", reason="insufficient_bidirectional_reference")
                continue
            positions = [float(np.median(arcs[side])) for side in sides]
            areas = [float(np.median([rows[j]["diagnostic_area_mm2"] for j in side])) for side in sides]
            reference = float(np.interp(arcs[k], positions, areas))
            row["status"] = "evaluable_candidate_only"
            if row["diagnostic_area_mm2"] <= reference * parameters.area_ratio_trigger: flags.append(k)
        groups = np.split(np.asarray(flags, dtype=int), np.flatnonzero(np.diff(flags) != 1) + 1) if flags else []
        for group in groups:
            if len(group) < parameters.minimum_candidate_sections: continue
            k = min(group, key=lambda j: rows[j]["diagnostic_area_mm2"])
            result["candidates"].append({"candidate_id": f"candidate-{len(result['candidates']) + 1:03}",
                "kind": "experimental_candidate", "branch_id": branch["branch_id"],
                "sample_ijk": rows[k]["sample_ijk"], "world_ras_mm": rows[k]["world_ras_mm"],
                "interval_s_mm": [rows[group[0]]["s_mm"], rows[group[-1]]["s_mm"]], "supporting_sections": int(len(group))})
        result["branches"].append({"branch_id": branch["branch_id"], "sections": rows,
            "evaluable_sections": sum(r["status"] == "evaluable_candidate_only" for r in rows),
            "abstained_sections": sum(r["status"] == "abstained" for r in rows)})
    if len(result["candidates"]) > 128: raise CandidateInputError("candidate_resource_limit")
    evaluable = sum(b["evaluable_sections"] for b in result["branches"])
    result["status"] = "candidate_preview" if result["candidates"] else "no_candidates_in_evaluable_sections" if evaluable else "abstained"
    result["reason"] = None if evaluable else "no_evaluable_reference_support"
    if len(json.dumps(result, allow_nan=False).encode()) > MAX_OUTPUT_BYTES: raise CandidateInputError("preview_output_resource_limit")
    return result
