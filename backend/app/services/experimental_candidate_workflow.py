"""Separate offline array workflow. No route, worker, file access or persistence."""
from copy import deepcopy

from app.services.experimental_branches import extract_branch_graph
from app.services.experimental_candidates import CandidateInputError, extract_candidates


def automatic_candidate_preview(mask, geometry, spacing, source, parameters):
    """Return complete graph evidence plus an existing-format preview, or abstain.

    Caller supplies authorized arrays. No extraction result is a clinical finding.
    A refused branch refuses the entire sampling operation; never silently omit it.
    """
    graph = extract_branch_graph(mask, geometry, spacing, source)
    output = {
        "schema_version": "experimental-automatic-candidates/0.1",
        "notice": "EXPERIMENTAL — NOT A DIAGNOSIS", "status": "abstained",
        "measurement_status": "measurement_unavailable_no_validated_gate",
        "graph": graph, "preview": None, "reason": None,
    }
    if graph["status"] != "experimental_tree":
        output["reason"] = "automatic_branch_graph_refused"
        return output
    branches = [{key: deepcopy(branch[key]) for key in (
        "branch_id", "ordered", "points_ijk", "junctions_s_mm", "mask_sha256", "geometry_fingerprint"
    )} for branch in graph["branches"]]
    try:
        preview = extract_candidates(mask, geometry, spacing, source, branches, parameters)
    except CandidateInputError as failure:
        output["reason"] = "candidate_sampling_refused:" + str(failure)
        return output
    output.update(status="experimental_workflow_completed", preview=preview)
    return output
