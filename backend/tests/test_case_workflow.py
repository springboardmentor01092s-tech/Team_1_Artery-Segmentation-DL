"""Tiny synthetic inputs only; no model, dataset or application DB access."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.models import Case, CaseReview, SegmentationResult
from app.models.audit import AuditEvent
from app.routers import case_workflow, segmentation
from test_segmentation_api import seed, volume


@pytest.fixture
def saved_run(client, account, monkeypatch):
    case_id, headers = seed(client, account)
    monkeypatch.setattr(settings, "VASCULAI_MODEL_CHECKPOINT", "synthetic-only")
    def execute(source, destination, threshold):
        destination.mkdir(parents=True)
        for name in ("prediction_mask.nii.gz", "probabilities.nii.gz"):
            (destination / name).write_bytes(volume())
        return {"source_sha256": segmentation.source_sha256(source), "checkpoint_sha256": "a" * 64,
                "threshold": threshold, "clinical_validation": False, "experimental": True}
    monkeypatch.setattr(segmentation, "execute_inference", execute)
    result = client.post(f"/api/v1/cases/{case_id}/segmentations", headers=headers, json={})
    assert result.status_code == 201, result.text
    return case_id, headers, result.json()["id"]


def payload(run, **changes):
    return {"segmentation_result_id": run, "outcome": "accepted_for_research",
            "acknowledge_research_only": True, **changes}


def test_no_run_never_infers_analysis_or_review_from_legacy_status(client, account, db):
    case_id, headers = seed(client, account)
    db.get(Case, case_id).status = "complete"
    db.commit()
    data = client.get(f"/api/v1/cases/{case_id}/workflow", headers=headers).json()
    assert data["case_status"] == "pending"
    assert data["model_analysis"]["available"] is False
    assert data["review"] is None
    assert data["clinical_validation"] is False


def test_actual_record_drives_progress_and_review_is_idempotent(client, saved_run, db):
    case_id, headers, run = saved_run
    url = f"/api/v1/cases/{case_id}"
    loaded = client.get(url + "/workflow", headers=headers)
    assert loaded.headers["cache-control"] == "no-store"
    data = loaded.json()
    assert data["case_status"] == "awaiting_review"
    assert data["model_analysis"]["run"]["segmentation_result_id"] == run
    assert data["review"] is None
    request = payload(run, note=" Inspected synthetic output for research workflow. ")
    first = client.post(url + "/reviews", headers=headers, json=request)
    assert first.status_code == 201, first.text
    assert first.headers["cache-control"] == "no-store"
    review = first.json()["review"]
    assert first.json()["case_status"] == "complete"
    assert review["reviewer_id"] > 0 and review["reviewer_role"] == "Clinician"
    assert review["reviewed_at"] and review["scope"] == "research_workflow_v1"
    assert review["note"] == "Inspected synthetic output for research workflow."
    assert review["current"] is True
    repeat = client.post(url + "/reviews", headers=headers, json=request)
    assert repeat.status_code == 200 and repeat.json()["review"]["id"] == review["id"]
    assert db.scalar(select(func.count()).select_from(CaseReview)) == 1
    assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "case.research_review_recorded")) == 1
    assert client.get(url, headers=headers).json()["status"] == "complete"


@pytest.mark.parametrize("role,expected", [("Admin", 201), ("Clinician", 201), ("Researcher", 403), ("DataScientist", 403)])
def test_review_reuses_existing_writer_roles(client, account, saved_run, role, expected):
    case_id, _, run = saved_run
    _, headers = account(role)
    url = f"/api/v1/cases/{case_id}"
    assert client.get(url + "/workflow", headers=headers).status_code == 200
    assert client.post(url + "/reviews", headers=headers, json=payload(run)).status_code == expected
    assert client.get(url + "/workflow").status_code == 401
    assert client.post(url + "/reviews", json=payload(run)).status_code == 401


def test_changes_requested_is_not_complete_and_requires_reason(client, saved_run):
    case_id, headers, run = saved_run
    url = f"/api/v1/cases/{case_id}/reviews"
    assert client.post(url, headers=headers, json=payload(run, outcome="changes_requested", note=" ")).status_code == 422
    response = client.post(url, headers=headers, json=payload(run, outcome="changes_requested", note="Reinspect the saved output."))
    assert response.status_code == 201
    assert response.json()["case_status"] == "changes_requested"
    assert client.post(url, headers=headers, json=payload(run)).status_code == 409


@pytest.mark.parametrize("extra", [{"acknowledge_research_only": False}, {"acknowledge_research_only": 1},
    {"reviewer_id": 999}, {"reviewed_at": "2026-01-01"}, {"validated": True}, {"outcome": "clinically_validated"}])
def test_untrusted_review_claims_are_rejected(client, saved_run, extra):
    case_id, headers, run = saved_run
    assert client.post(f"/api/v1/cases/{case_id}/reviews", headers=headers, json=payload(run, **extra)).status_code == 422


def test_wrong_case_missing_case_and_superseded_run_fail_closed(client, saved_run, db):
    case_id, headers, run = saved_run
    assert client.post(f"/api/v1/cases/{case_id + 1}/reviews", headers=headers, json=payload(run)).status_code == 404
    other = Case(patient_id=db.get(Case, case_id).patient_id, case_code="OTHER", modality="CTA")
    db.add(other); db.commit()
    assert client.post(f"/api/v1/cases/{other.id}/reviews", headers=headers, json=payload(run)).status_code == 409
    new = client.post(f"/api/v1/cases/{case_id}/segmentations", headers=headers, json={}).json()["id"]
    assert new != run
    assert client.post(f"/api/v1/cases/{case_id}/reviews", headers=headers, json=payload(run)).status_code == 409


def test_new_run_invalidates_completion_and_preserves_review(client, saved_run):
    case_id, headers, run = saved_run
    url = f"/api/v1/cases/{case_id}"
    assert client.post(url + "/reviews", headers=headers, json=payload(run)).status_code == 201
    assert client.post(url + "/segmentations", headers=headers, json={}).status_code == 201
    data = client.get(url + "/workflow", headers=headers).json()
    assert data["case_status"] == "awaiting_review" and data["review"] is None
    assert len(data["review_history"]) == 1 and data["review_history"][0]["current"] is False
    assert client.get(url, headers=headers).json()["status"] == "awaiting_review"


def test_replaced_input_invalidates_review_without_erasing_history(client, saved_run):
    case_id, headers, run = saved_run
    url = f"/api/v1/cases/{case_id}"
    assert client.post(url + "/reviews", headers=headers, json=payload(run)).status_code == 201
    assert client.post(url + "/volume", headers=headers, files={"file": ("new.nii.gz", volume((7, 8, 9)))}).status_code == 200
    data = client.get(url + "/workflow", headers=headers).json()
    assert data["case_status"] == "pending" and not data["model_analysis"]["available"]
    assert data["review_history"][0]["current"] is False
    assert client.get(url, headers=headers).json()["status"] == "pending"
    assert client.post(url + "/reviews", headers=headers, json=payload(run)).status_code == 409


@pytest.mark.parametrize("kind", ["source", "missing_mask", "mask_changed", "missing_provenance", "invalid_latest"])
def test_unreliable_or_changed_evidence_never_keeps_a_current_review(client, saved_run, db, kind):
    case_id, headers, run = saved_run
    url = f"/api/v1/cases/{case_id}"
    assert client.post(url + "/reviews", headers=headers, json=payload(run)).status_code == 201
    if kind == "source":
        (segmentation.UPLOAD_DIR / db.get(Case, case_id).volume_path).write_bytes(volume((3, 4, 5)))
    elif kind in {"missing_mask", "mask_changed"}:
        mask = segmentation.result_directory(run) / "prediction_mask.nii.gz"
        if kind == "missing_mask": mask.unlink()
        else: mask.write_bytes(volume((3, 4, 5)))
    elif kind == "missing_provenance":
        db.get(SegmentationResult, run).metadata_json = {}
        db.commit()
    else:
        db.add(SegmentationResult(id=str(uuid4()), case_id=case_id, source_volume_path="missing", metadata_json={},
                                  created_at=db.get(SegmentationResult, run).created_at + timedelta(seconds=1)))
        db.commit()
    data = client.get(url + "/workflow", headers=headers).json()
    assert data["case_status"] != "complete" and data["review"] is None
    assert data["review_history"][0]["current"] is False
    assert client.post(url + "/reviews", headers=headers, json=payload(run)).status_code == 409


def test_tied_run_timestamps_abstain_instead_of_selecting_a_reviewed_run(client, saved_run, db):
    case_id, headers, run = saved_run
    first = db.get(SegmentationResult, run)
    db.add(SegmentationResult(id=str(uuid4()), case_id=case_id, source_volume_path=first.source_volume_path,
                              metadata_json=first.metadata_json, created_at=first.created_at))
    db.commit()
    data = client.get(f"/api/v1/cases/{case_id}/workflow", headers=headers).json()
    assert data["model_analysis"]["available"] is False
    assert "ambiguous" in data["model_analysis"]["reason"]
    assert client.post(f"/api/v1/cases/{case_id}/reviews", headers=headers, json=payload(run)).status_code == 409


def test_change_during_review_rolls_back_decision_status_and_audit(client, saved_run, monkeypatch, db):
    case_id, headers, run = saved_run
    original = case_workflow.model_evidence
    calls = 0
    def changing(*args):
        nonlocal calls
        result, reason = original(*args); calls += 1
        if calls == 2: result = dict(result, mask_sha256="b" * 64)
        return result, reason
    monkeypatch.setattr(case_workflow, "model_evidence", changing)
    assert client.post(f"/api/v1/cases/{case_id}/reviews", headers=headers, json=payload(run)).status_code == 409
    assert db.scalar(select(func.count()).select_from(CaseReview)) == 0
    assert db.get(Case, case_id).status == "awaiting_review"
    assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "case.research_review_recorded")) == 0


def test_postgres_competing_reviews_are_serialized(client, saved_run, monkeypatch, db):
    if db.bind.dialect.name != "postgresql":
        pytest.skip("PostgreSQL row-lock concurrency check")
    case_id, headers, run = saved_run
    barrier = Barrier(2)
    original = case_workflow.case_for
    def synchronized(*args, **kwargs):
        if kwargs.get("lock"): barrier.wait(timeout=10)
        return original(*args, **kwargs)
    monkeypatch.setattr(case_workflow, "case_for", synchronized)
    def request(note):
        return client.post(f"/api/v1/cases/{case_id}/reviews", headers=headers, json=payload(run, note=note)).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(request, ["First independent research decision", "Competing decision"]))
    assert sorted(codes) == [201, 409]
    assert db.scalar(select(func.count()).select_from(CaseReview)) == 1
