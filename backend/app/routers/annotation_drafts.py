"""No assignments, submission, training or clinical-report endpoint."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, Query, Response
from sqlalchemy.exc import IntegrityError

from app.routers.cases import ClinicalWriter, DatabaseSession
from app.schemas.annotation_draft import CreateDraft, UpdateDraft, DraftResponse, DraftIndex
from app.services import annotation_drafts as service

router = APIRouter(prefix="/cases/{case_id}/annotation-drafts", tags=["Unverified annotation drafts"])
CaseId = Annotated[int, Path(ge=1, le=2147483647)]


def finish(response, operation, *args):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    try:
        return operation(*args)
    except IntegrityError:
        args[0].rollback()
        raise HTTPException(409, "Draft authorization, source binding or revision conflict; refresh before retrying.") from None


@router.post("", status_code=201, response_model=DraftResponse)
def create(case_id: CaseId, data: CreateDraft, response: Response, actor: ClinicalWriter, db: DatabaseSession):
    return finish(response, service.create_draft, db, actor, case_id, data.document)


@router.get("", response_model=DraftIndex)
def discover(case_id: CaseId, response: Response, actor: ClinicalWriter, db: DatabaseSession,
             segmentation_result_id: UUID | None = None,
             limit: Annotated[int, Query(ge=1, le=50)] = 20,
             offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0):
    return finish(response, service.list_drafts, db, actor, case_id,
                  str(segmentation_result_id) if segmentation_result_id else None, limit, offset)


@router.get("/{draft_id}", response_model=DraftResponse)
def retrieve(case_id: CaseId, draft_id: UUID, response: Response, actor: ClinicalWriter, db: DatabaseSession):
    return finish(response, service.read_draft, db, actor, case_id, str(draft_id))


@router.put("/{draft_id}", response_model=DraftResponse)
def update(case_id: CaseId, draft_id: UUID, data: UpdateDraft, response: Response, actor: ClinicalWriter, db: DatabaseSession):
    return finish(response, service.update_draft, db, actor, case_id, str(draft_id), data.document, data.expected_revision)


@router.delete("/{draft_id}", status_code=204)
def remove(case_id: CaseId, draft_id: UUID, response: Response, actor: ClinicalWriter, db: DatabaseSession,
           expected_revision: Annotated[int, Query(ge=1, le=2147483647)]):
    finish(response, service.delete_draft, db, actor, case_id, str(draft_id), expected_revision)
