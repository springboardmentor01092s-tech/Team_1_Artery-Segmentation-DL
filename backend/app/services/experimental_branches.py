"""CPU-only supplied-array skeleton trees. No IO, API, DB or provider registration.

An accepted digital tree is not a proof of anatomical centerline completeness.
Every original skeleton edge/vertex is retained; no pruning or graph repair.
"""
from importlib.metadata import version
from itertools import product
from uuid import UUID

import numpy as np
from scipy.ndimage import distance_transform_edt, label
from skimage.measure import euler_number

from app.services.experimental_candidates import CandidateInputError, _categorical, _geometry, mask_identity
from app.services.stenosis_geometry import geometry_fingerprint
from app.services.vessel_analysis import extract_centerline

MAX_SKELETON_VERTICES = 8192
MAX_GRAPH_BRANCHES = 8  # Existing candidate workflow limit, never drop extra branches.
OFFSETS = tuple(p for p in product((-1, 0, 1), repeat=3) if p != (0, 0, 0))
UNCERTAINTY = [
    "unvalidated_digital_skeleton_not_anatomical_centerline",
    "terminal_or_subvoxel_branch_completeness_not_proven",
    "nearest_skeleton_support_check_is_not_anatomical_validation",
]


def _inputs(mask, geometry, spacing, source):
    fields = {"source_sha256", "mask_sha256", "geometry_fingerprint", "mask_role", "parent_segmentation_result_id", "target_label"}
    if not isinstance(source, dict) or set(source) != fields or source["target_label"] != 1:
        raise CandidateInputError("explicit_binary_source_binding_required")
    for key in ("source_sha256", "mask_sha256", "geometry_fingerprint"):
        value = source[key]
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise CandidateInputError("invalid_source_digest")
    if source["mask_role"] not in ("model_prediction", "reference_annotation", "supplied_segmentation"):
        raise CandidateInputError("explicit_mask_role_required")
    parent = source["parent_segmentation_result_id"]
    if source["mask_role"] == "model_prediction":
        try:
            if not isinstance(parent, str) or str(UUID(parent)) != parent:
                raise ValueError()
        except ValueError:
            raise CandidateInputError("prediction_parent_required") from None
    elif parent is not None:
        raise CandidateInputError("annotation_is_not_a_prediction")
    array = _categorical(mask, source["target_label"])
    if not np.isin(array, (0, 1)).all():
        raise CandidateInputError("binary_mask_required")
    g, affine, _ = _geometry(array, geometry, spacing)
    if mask_identity(array, 1) != source["mask_sha256"] or geometry_fingerprint(g, source["source_sha256"]) != source["geometry_fingerprint"]:
        raise CandidateInputError("source_identity_mismatch")
    return array.astype(bool, copy=False), g, affine


def extract_branch_graph(mask, geometry, spacing, source):
    """Retain raw 26-neighbor graph; admit only isolated-junction simple trees.

    Supplied arrays must already be authorized by the caller. This pure function
    neither obtains medical files nor establishes authorization or anatomical truth.
    """
    binary, g, affine = _inputs(mask, geometry, spacing, source)
    result = {
        "schema_version": "experimental-branch-graph/0.1", "notice": "EXPERIMENTAL — NOT A DIAGNOSIS",
        "method": {"id": "lee-26-tree-no-pruning", "version": "0.1.0", "scikit_image_version": version("scikit-image")},
        "source": dict(source), "geometry": g.model_dump(mode="json"),
        "status": "abstained", "reasons": [], "uncertainty": list(UNCERTAINTY),
        "nodes": [], "edges": [], "endpoints": [], "junctions": [], "branches": [],
        "diagnostics": {},
    }
    reasons, diagnostic = result["reasons"], result["diagnostics"]
    # No largest-component selection. Count both connectivities explicitly.
    _, components6 = label(binary)
    _, components26 = label(binary, structure=np.ones((3, 3, 3), dtype=bool))
    diagnostic.update(input_components_6=int(components6), input_components_26=int(components26))
    if not components26:
        reasons.append("empty_mask")
        return result
    if components6 != 1 or components26 != 1:
        reasons.append("disconnected_or_diagonal_only_source")
        return result
    if any(np.any(np.take(binary, face, axis=axis)) for axis in range(3) for face in (0, -1)):
        reasons.append("source_volume_truncation")
        return result
    # Diagnostics only: never fill a cavity or change the supplied mask.
    _, background_components = label(~binary)
    diagnostic.update(source_euler_26=int(euler_number(binary, connectivity=3)), enclosed_background_components=int(background_components - 1))
    if diagnostic["source_euler_26"] != 1 or background_components != 1:
        reasons.append("source_loop_cavity_or_non_tree_topology")
        return result
    skeleton, thinning = extract_centerline(binary, return_diagnostics=True)
    diagnostic["thinning"] = thinning
    diagnostic["skeleton_vertices"] = int(np.count_nonzero(skeleton))
    if diagnostic["skeleton_vertices"] > MAX_SKELETON_VERTICES:
        reasons.append("skeleton_graph_resource_limit")
        return result
    if np.any(skeleton & ~binary):
        reasons.append("skeleton_outside_source")
        return result
    if thinning["disappeared_components"] or thinning["fragmented_components"] or thinning["output_skeleton_component_count"] != 1:
        reasons.append("skeleton_component_loss_or_fragmentation")
        return result
    coordinates = np.argwhere(skeleton)  # Lexicographic original IJK order.
    lookup = {tuple(p): i for i, p in enumerate(coordinates)}
    adjacency = [[] for _ in coordinates]
    edges = []
    for i, point in enumerate(coordinates):
        for delta in OFFSETS:
            j = lookup.get(tuple(point + delta))
            if j is not None and j > i:
                edges.append([i, j]); adjacency[i].append(j); adjacency[j].append(i)
    for neighbors in adjacency:
        neighbors.sort()
    edges.sort()
    world = coordinates @ affine[:3, :3].T + affine[:3, 3]
    result["nodes"] = [{"node_id": i, "ijk": p.tolist(), "ras_mm": world[i].tolist(), "degree": len(adjacency[i])} for i, p in enumerate(coordinates)]
    result["edges"] = edges
    endpoints = [i for i, neighbors in enumerate(adjacency) if len(neighbors) == 1]
    junctions = [i for i, neighbors in enumerate(adjacency) if len(neighbors) > 2]
    endpoint_ids = {i: f"endpoint-{n:03}" for n, i in enumerate(endpoints, 1)}
    junction_ids = {i: f"junction-{n:03}" for n, i in enumerate(junctions, 1)}
    result["endpoints"] = [{"endpoint_id": endpoint_ids[i], "node_id": i} for i in endpoints]
    result["junctions"] = [{"junction_id": junction_ids[i], "node_id": i, "degree": len(adjacency[i])} for i in junctions]
    diagnostic["graph_cycle_rank"] = len(edges) - len(coordinates) + 1
    if len(coordinates) < 3 or any(not n for n in adjacency):
        reasons.append("insufficient_skeleton")
    if diagnostic["graph_cycle_rank"] != 0:
        reasons.append("skeleton_graph_cycle_or_local_adjacency_ambiguity")
    if any(j in junction_ids for i in junctions for j in adjacency[i]):
        reasons.append("ambiguous_adjacent_junctions")
    if reasons:
        return result  # Raw graph retained. Never collapse cycles/junction clusters.
    critical = set(endpoints + junctions)
    visited, paths = set(), []
    for start in sorted(critical):
        for neighbor in adjacency[start]:
            edge = tuple(sorted((start, neighbor)))
            if edge in visited:
                continue
            visited.add(edge)
            path, previous, current = [start, neighbor], start, neighbor
            while current not in critical:
                following = next(i for i in adjacency[current] if i != previous)
                edge = tuple(sorted((current, following)))
                if edge in visited:
                    raise CandidateInputError("unexpected_reused_skeleton_edge")
                visited.add(edge); path.append(following)
                previous, current = current, following
            paths.append(path if path[0] < path[-1] else path[::-1])
    paths.sort(key=tuple)
    if visited != {tuple(edge) for edge in edges} or set(i for path in paths for i in path) != set(range(len(coordinates))):
        raise CandidateInputError("incomplete_skeleton_partition")
    for n, path in enumerate(paths, 1):
        points = world[path]
        arcs = np.r_[0., np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
        ends = [{"node_id": i, "endpoint_id": endpoint_ids.get(i), "junction_id": junction_ids.get(i)} for i in (path[0], path[-1])]
        result["branches"].append({
            "branch_id": f"branch-{n:03}", "node_ids": path, "ordered": True,
            "points_ijk": coordinates[path].tolist(), "points_ras_mm": points.tolist(),
            "arc_mm": arcs.tolist(), "length_mm": float(arcs[-1]), "ends": ends,
            "junctions_s_mm": [float(arcs[k]) for k in (0, len(path) - 1) if path[k] in junction_ids],
            "mask_sha256": source["mask_sha256"], "geometry_fingerprint": source["geometry_fingerprint"],
        })
    if len(paths) > MAX_GRAPH_BRANCHES:
        reasons.append("branch_count_resource_limit")
    if any(len(path) < 3 for path in paths):
        reasons.append("short_spur_or_branch_not_resolved")
    # A conservative support diagnostic catches large missed limbs. This is NOT
    # a certificate that every tiny anatomical branch survived thinning.
    clearance = distance_transform_edt(binary, sampling=spacing)
    distance, nearest = distance_transform_edt(~skeleton, sampling=spacing, return_indices=True)
    allowance = clearance[tuple(nearest)] + .5 * np.linalg.norm(spacing)
    excess = distance[binary] - allowance[binary]
    diagnostic["unsupported_foreground_voxels"] = int(np.count_nonzero(excess > 1e-9))
    diagnostic["maximum_support_excess_mm"] = float(np.max(excess))
    if diagnostic["unsupported_foreground_voxels"]:
        reasons.append("source_region_not_supported_by_skeleton")
    diagnostic["all_skeleton_edges_partitioned"] = True
    diagnostic["all_skeleton_vertices_retained"] = True
    if not reasons:
        result["status"] = "experimental_tree"
    return result
