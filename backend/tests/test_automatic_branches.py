"""Synthetic-only tests. No conftest, database, filesystem medical data or models."""
from copy import deepcopy
import json

import numpy as np
import pytest

from app.services import experimental_branches as graph_module
from app.services.experimental_branches import extract_branch_graph
from app.services.experimental_candidate_workflow import automatic_candidate_preview
from app.services.experimental_candidates import CandidateInputError, ResearchParameters
from automatic_branch_fixtures import CONFIGURATIONS, bound_source, spatial_fixture, y_fixture

PARAMETERS = ResearchParameters(.5, 8., 1., 4., 8., 4, .65, 2, 5.)
RESULTS = []


def assert_partition(graph):
    edges = [tuple(edge) for branch in graph["branches"] for edge in zip(branch["node_ids"], branch["node_ids"][1:])]
    canonical = [tuple(sorted(edge)) for edge in edges]
    assert len(canonical) == len(set(canonical))
    assert set(canonical) == {tuple(edge) for edge in graph["edges"]}
    assert {n for b in graph["branches"] for n in b["node_ids"]} == {n["node_id"] for n in graph["nodes"]}


@pytest.mark.parametrize("configuration", CONFIGURATIONS, ids=lambda c: c[0])
@pytest.mark.parametrize("focal", [False, True], ids=["constant", "focal"])
def test_independent_world_spatial_matrix(configuration, focal):
    mask, geometry, spacing, source, truth, direct_world = spatial_fixture(configuration, focal)
    original = mask.copy(), deepcopy(source)
    result = automatic_candidate_preview(mask, geometry, spacing, source, PARAMETERS)
    graph, preview = result["graph"], result["preview"]
    assert graph["source"] == source and graph["geometry"] == geometry.model_dump(mode="json")
    maximum_center_error = None
    if graph["nodes"]:
        # Independent world formula and analytic curve membership, not just an
        # inverse-affine round trip or an array-k interval.
        ijk = np.array([n["ijk"] for n in graph["nodes"]])
        actual_world = np.array([n["ras_mm"] for n in graph["nodes"]])
        assert np.allclose(actual_world, direct_world(ijk), atol=1e-10)
        _, distance, radius = truth(actual_world)
        assert np.all(distance <= radius + 1e-9)
        maximum_center_error = float(np.max(distance))
    if graph["status"] == "experimental_tree":
        assert_partition(graph)
        assert len(graph["branches"]) == 1 and len(graph["endpoints"]) == 2 and not graph["junctions"]
        assert maximum_center_error <= np.linalg.norm(spacing)
    candidates = preview["candidates"] if preview else []
    true_positive, false_positive = 0, 0
    for candidate in candidates:
        arc, distance, radius = truth(np.array(candidate["world_ras_mm"]))
        # Independent 3D ground-truth region: arc and radial membership.
        correct = focal and abs(float(arc)) <= 2. + 1e-9 and float(distance) <= float(radius) + 1e-9
        true_positive += int(correct); false_positive += int(not correct)
    if preview:
        assert preview["source"] == source
        assert preview["measurement_status"] == "measurement_unavailable_no_validated_gate"
        assert preview["parameters"] == PARAMETERS.__dict__
    else:
        assert result["status"] == "abstained" and result["reason"]
    # Contract tests check truthful rejection. Separate fixed engineering
    # criteria in the external protocol count abstentions/misses as failures.
    assert not false_positive
    encoded = json.dumps(result, allow_nan=False)
    for forbidden in ('"percentage_narrowing"', '"severity"', '"confidence"', '"validation_gate"'):
        assert forbidden not in encoded
    assert np.array_equal(mask, original[0]) and source == original[1]
    evaluable = sum(b["evaluable_sections"] for b in preview["branches"]) if preview else 0
    sections = sum(len(b["sections"]) for b in preview["branches"]) if preview else 0
    RESULTS.append({"fixture": configuration[0], "focal": focal, "spacing_mm": str(tuple(spacing)),
                    "phase_mm": str(configuration[4]), "graph_status": graph["status"], "graph_reasons": ";".join(graph["reasons"]),
                    "branches": len(graph["branches"]), "endpoints": len(graph["endpoints"]), "junctions": len(graph["junctions"]),
                    "workflow_status": result["status"], "workflow_reason": result["reason"], "candidates": len(candidates),
                    "true_positive": true_positive, "false_positive": false_positive,
                    "false_negative": int(focal and not true_positive), "evaluable_sections": evaluable,
                    "total_sections": sections, "maximum_center_error_mm": maximum_center_error,
                    "engineering_pass": graph["status"] == "experimental_tree" and preview is not None and bool(evaluable)
                    and (bool(true_positive) if focal else not candidates)})


@pytest.mark.parametrize("radius", [1., 2., 3.])
def test_true_y_preserves_all_three_limbs_and_single_junction(radius):
    args = y_fixture(radius)
    graph = extract_branch_graph(*args)
    assert graph["status"] == "experimental_tree"
    assert len(graph["branches"]) == 3 and len(graph["endpoints"]) == 3 and len(graph["junctions"]) == 1
    assert_partition(graph)
    tips = np.array([[36, 36, 8], [18, 36, 60], [54, 36, 60]])
    endpoints = np.array([graph["nodes"][e["node_id"]]["ras_mm"] for e in graph["endpoints"]])
    distances = np.linalg.norm(tips[:, None] - endpoints[None, :], axis=-1)
    assert all(np.min(row) <= radius + np.sqrt(3) for row in distances)
    assert len(set(np.argmin(distances, axis=1))) == 3
    assert all(len(b["junctions_s_mm"]) == 1 for b in graph["branches"])
    # Stable graph/IDs/order, no automatic spurs removal or run-specific IDs.
    assert graph == extract_branch_graph(*args)


def test_y_workflow_retains_each_branch_and_junction_exclusions():
    result = automatic_candidate_preview(*y_fixture(), PARAMETERS)
    assert result["status"] == "experimental_workflow_completed"
    assert len(result["preview"]["branches"]) == 3
    for branch in result["preview"]["branches"]:
        assert any(row["reason"] == "junction_exclusion" for row in branch["sections"])


@pytest.mark.parametrize("width", [2, 4, 6])
def test_even_width_loss_abstains_without_fallback_or_invented_points(width):
    mask, g, spacing, _ = y_fixture()
    mask[:] = 0; mask[15:55, 30:30 + width, 30:30 + width] = 1
    result = automatic_candidate_preview(mask, g, spacing, bound_source(mask, g), PARAMETERS)
    assert result["status"] == "abstained" and result["preview"] is None
    assert "skeleton_component_loss_or_fragmentation" in result["graph"]["reasons"]
    assert not result["graph"]["nodes"]


@pytest.mark.parametrize("defect", ["empty", "disconnected", "loop", "cavity", "truncated"])
def test_unreliable_source_topologies_refuse_globally(defect):
    mask, g, spacing, _ = y_fixture()
    if defect == "empty": mask[:] = 0
    if defect == "disconnected": mask[3:5, 3:5, 3:5] = 1
    if defect == "loop":
        x, y, z = np.indices(mask.shape); mask = ((np.hypot(x - 36, y - 36) - 12) ** 2 + (z - 36) ** 2 <= 3 ** 2).astype(np.uint8)
    if defect == "cavity": mask[36, 36, 20] = 0
    if defect == "truncated": mask[0:10, 35:38, 7:10] = 1
    result = automatic_candidate_preview(mask, g, spacing, bound_source(mask, g), PARAMETERS)
    assert result["status"] == "abstained" and result["preview"] is None and result["graph"]["reasons"]


def test_lost_large_limb_is_not_hidden_by_single_component_diagnostic(monkeypatch):
    args = y_fixture()
    skeleton, _ = graph_module.extract_centerline(args[0], True)
    skeleton[:35] = False  # Deliberately missing left limb in a test double.
    monkeypatch.setattr(graph_module, "extract_centerline", lambda *_a, **_k: (skeleton, {
        "input_component_count": 1, "output_skeleton_component_count": 1,
        "disappeared_components": [], "fragmented_components": {},
    }))
    graph = extract_branch_graph(*args)
    assert graph["status"] == "abstained"
    assert "source_region_not_supported_by_skeleton" in graph["reasons"]
    assert graph["diagnostics"]["unsupported_foreground_voxels"] > 0


def test_short_spur_is_retained_in_evidence_then_refused(monkeypatch):
    mask, g, spacing, _ = y_fixture()
    skeleton = np.zeros(mask.shape, dtype=bool)
    skeleton[36, 36, 8:37] = True
    for n in range(1, 15): skeleton[36 - n, 36, 36 + n] = True
    skeleton[37, 36, 37] = True
    assert not np.any(skeleton & ~mask)
    monkeypatch.setattr(graph_module, "extract_centerline", lambda *_a, **_k: (skeleton, {
        "input_component_count": 1, "output_skeleton_component_count": 1, "disappeared_components": [], "fragmented_components": {},
    }))
    graph = extract_branch_graph(mask, g, spacing, bound_source(mask, g))
    assert graph["status"] == "abstained" and "short_spur_or_branch_not_resolved" in graph["reasons"]
    assert any(len(b["node_ids"]) == 2 for b in graph["branches"])
    assert_partition(graph)


def test_ambiguous_junction_cluster_keeps_raw_edges_without_collapsing(monkeypatch):
    mask, g, spacing, _ = y_fixture()
    skeleton = np.zeros(mask.shape, dtype=bool)
    skeleton[36, 36, 25:40] = True; skeleton[37, 36, 35] = True
    monkeypatch.setattr(graph_module, "extract_centerline", lambda *_a, **_k: (skeleton, {
        "input_component_count": 1, "output_skeleton_component_count": 1, "disappeared_components": [], "fragmented_components": {},
    }))
    graph = extract_branch_graph(mask, g, spacing, bound_source(mask, g))
    assert graph["status"] == "abstained" and graph["edges"] and len(graph["nodes"]) == int(skeleton.sum())
    assert "skeleton_graph_cycle_or_local_adjacency_ambiguity" in graph["reasons"]
    assert not graph["branches"]


def test_all_branches_retained_if_candidate_sampler_refuses(monkeypatch):
    import app.services.experimental_candidate_workflow as workflow
    def refuse(*_a, **_k): raise CandidateInputError("unordered_or_sharply_turning_centerline")
    monkeypatch.setattr(workflow, "extract_candidates", refuse)
    result = workflow.automatic_candidate_preview(*y_fixture(), PARAMETERS)
    assert len(result["graph"]["branches"]) == 3 and result["preview"] is None
    assert result["reason"] == "candidate_sampling_refused:unordered_or_sharply_turning_centerline"


@pytest.mark.parametrize("defect", ["source", "mask", "geometry", "multilabel", "parent"])
def test_source_bindings_never_bypassed(defect):
    mask, g, spacing, source = y_fixture()
    if defect == "source": source["source_sha256"] = "b" * 64
    if defect == "mask": mask[36, 36, 20] = 0
    if defect == "geometry": source["geometry_fingerprint"] = "b" * 64
    if defect == "multilabel": mask[1, 1, 1] = 2
    if defect == "parent": source["parent_segmentation_result_id"] = "12345678-1234-4567-890a-123456789abc"
    with pytest.raises(CandidateInputError): extract_branch_graph(mask, g, spacing, source)


def test_graph_resource_limit_precedes_adjacency_and_support_allocation(monkeypatch):
    monkeypatch.setattr(graph_module, "MAX_SKELETON_VERTICES", 2)
    graph = extract_branch_graph(*y_fixture())
    assert graph["status"] == "abstained" and graph["reasons"] == ["skeleton_graph_resource_limit"]
    assert not graph["nodes"] and not graph["edges"]
