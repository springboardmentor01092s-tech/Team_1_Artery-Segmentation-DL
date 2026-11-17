"""Authenticated research review, using existing case RBAC and audit policy."""
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import Case, CaseReview
from app.routers.cases import AuthenticatedCaseReader, ClinicalWriter, DatabaseSession
from app.routers.segmentation import readable_cases
from app.schemas.case_review import CaseReviewRequest, CaseWorkflowResponse
from app.services.audit import record_event
from app.services.case_workflow import FINGERPRINT_FIELDS, model_evidence, review_matches, workflow_state

router = APIRouter(prefix="/cases", tags=["Research case workflow"])


def case_for(db, case_id, lock=False):
    statement = readable_cases().where(Case.id == case_id)
    case = db.scalar(statement.with_for_update() if lock else statement)
    if case is None:
        raise HTTPException(404, "Case not found")
    return case


@router.get("/{case_id}/workflow", response_model=CaseWorkflowResponse)
def get_workflow(case_id: int, response: Response, current_user: AuthenticatedCaseReader, db: DatabaseSession):
    response.headers["Cache-Control"] = "no-store"
    result = workflow_state(db, case_for(db, case_id))
    record_event(db, "case.workflow_read", current_user.id, case_id)
    db.commit()
    return result


@router.post("/{case_id}/reviews", status_code=201, response_model=CaseWorkflowResponse)
def record_review(case_id: int, data: CaseReviewRequest, response: Response,
                  current_user: ClinicalWriter, db: DatabaseSession):
    response.headers["Cache-Control"] = "no-store"
    case = case_for(db, case_id, lock=True)
    evidence, reason = model_evidence(db, case)
    if not evidence or evidence["segmentation_result_id"] != str(data.segmentation_result_id):
        raise HTTPException(409, reason or "Refresh the case and review its latest current saved run.")
    existing = db.scalar(select(CaseReview).where(CaseReview.segmentation_result_id == str(data.segmentation_result_id)))
    if existing:
        if (existing.reviewer_id == current_user.id and existing.outcome == data.outcome
                and existing.note == data.note and review_matches(existing, evidence)):
            response.status_code = 200
            return workflow_state(db, case)
        raise HTTPException(409, "This run already has an immutable review. A new or changed output requires a new run and review.")
    review = CaseReview(id=str(uuid4()), case_id=case.id, segmentation_result_id=str(data.segmentation_result_id),
                        reviewer_id=current_user.id, reviewer_role=current_user.role, outcome=data.outcome, note=data.note,
                        **{key: evidence[key] for key in FINGERPRINT_FIELDS})
    try:
        db.add(review)
        case.status = "complete" if data.outcome == "accepted_for_research" else "changes_requested"
        record_event(db, "case.research_review_recorded", current_user.id, case.id)
        db.flush()
        checked, _ = model_evidence(db, case)
        if checked != evidence:
            db.rollback()
            raise HTTPException(409, "Source or outputs changed during review; refresh and inspect them again.")
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "A competing review was recorded; refresh the case before continuing.") from None
    return workflow_state(db, case)
