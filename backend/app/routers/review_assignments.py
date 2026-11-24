from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy.exc import IntegrityError

from app.routers.admin import Admin
from app.routers.cases import ClinicalWriter, DatabaseSession
from app.routers.segmentation import SourceSnapshotResponse, snapshot_source
from app.core.config import settings
from app.schemas.review_assignment import AssignReaders, SaveReviewNote
from app.services import review_assignments as service
from app.services.audit import record_event
from app.schemas.review_annotation import SaveReviewAnnotation,SubmitReview
from app.services import review_annotations,review_submissions
from app.schemas.review_amendment import CreateReviewAmendment
from app.services import review_amendments

router = APIRouter(tags=["Unverified original CT review"])


def call(response, operation, db, *args):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    try:return operation(db, *args)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Review assignment, source or note revision conflict") from None


@router.get("/review-studies/source")
def preview(case_id: Annotated[int, Query(ge=1, le=2147483647)], response: Response,
            actor: Admin, db: DatabaseSession):
    return call(response, service.source_preview, db, actor, case_id)


@router.post("/review-studies", status_code=201)
def create(data: AssignReaders, response: Response, actor: Admin, db: DatabaseSession):
    return call(response, service.assign, db, actor, data)


@router.get("/review-assignments")
def own(response: Response, actor: ClinicalWriter, db: DatabaseSession,
        limit: Annotated[int, Query(ge=1, le=50)] = 20, offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0):
    return call(response, service.list_own, db, actor, limit, offset)


@router.get("/review-assignments/{assignment_id}")
def detail(assignment_id: UUID, response: Response, actor: ClinicalWriter, db: DatabaseSession):
    return call(response, service.detail, db, actor, str(assignment_id))


@router.get("/review-assignments/{assignment_id}/source")
def original_ct(assignment_id: UUID, actor: ClinicalWriter, db: DatabaseSession):
    _, study = service.own_assignment(db, actor, str(assignment_id))
    _, _, path, _, compressed = service.verify_assigned_source(db, study)
    try:
        snapshot = snapshot_source(path, study.source_json["source_sha256"], compressed,
            max_bytes=min(512, settings.MAX_VOLUME_COMPRESSED_MB if compressed else settings.MAX_VOLUME_UNCOMPRESSED_FILE_MB)*1024*1024)
    except (OSError, ValueError):
        raise HTTPException(409, "Original CT snapshot could not be verified") from None
    try:
        record_event(db, "review.original_ct_read", actor.id, study.case_id);db.commit()
        return SourceSnapshotResponse(snapshot, compressed)
    except BaseException:
        snapshot.close();raise


@router.get("/review-assignments/{assignment_id}/draft")
def notes(assignment_id: UUID, response: Response, actor: ClinicalWriter, db: DatabaseSession):
    return call(response, service.get_note, db, actor, str(assignment_id))


@router.put("/review-assignments/{assignment_id}/draft")
def save_notes(assignment_id: UUID, data: SaveReviewNote, response: Response,
               actor: ClinicalWriter, db: DatabaseSession):
    result, created = call(response, service.save_note, db, actor, str(assignment_id), data)
    response.status_code = 201 if created else 200
    return result


@router.get('/review-assignments/{assignment_id}/annotation-draft')
def annotation(assignment_id: UUID,response: Response,actor: ClinicalWriter,db: DatabaseSession):
    return call(response,review_annotations.read,db,actor,str(assignment_id))


@router.put('/review-assignments/{assignment_id}/annotation-draft')
def save_annotation(assignment_id: UUID,data: SaveReviewAnnotation,response: Response,actor: ClinicalWriter,db: DatabaseSession):
    result,created=call(response,review_annotations.save,db,actor,str(assignment_id),data)
    response.status_code=201 if created else 200
    return result


@router.get('/review-assignments/{assignment_id}/annotation-history')
def annotation_history(assignment_id: UUID,response: Response,actor: ClinicalWriter,db: DatabaseSession,
    limit: Annotated[int,Query(ge=1,le=50)]=20,offset: Annotated[int,Query(ge=0,le=1_000_000)]=0):
    return call(response,review_annotations.history,db,actor,str(assignment_id),limit,offset)


@router.get('/review-assignments/{assignment_id}/submission')
def independent_submission(assignment_id: UUID,response: Response,actor: ClinicalWriter,db: DatabaseSession):
    return call(response,review_submissions.read,db,actor,str(assignment_id))


@router.post('/review-assignments/{assignment_id}/submit',status_code=201)
def submit_independent_review(assignment_id: UUID,data: SubmitReview,response: Response,actor: ClinicalWriter,db: DatabaseSession):
    result,created=call(response,review_submissions.submit,db,actor,str(assignment_id),data)
    response.status_code=201 if created else 200
    return result


@router.get('/review-assignments/{assignment_id}/amendments')
def amendments(assignment_id: UUID,response: Response,actor: ClinicalWriter,db: DatabaseSession):
    return call(response,review_amendments.read,db,actor,str(assignment_id))


@router.post('/review-assignments/{assignment_id}/amendments',status_code=201)
def add_amendment(assignment_id: UUID,data: CreateReviewAmendment,response: Response,
                  actor: ClinicalWriter,db: DatabaseSession):
    result,created=call(response,review_amendments.append,db,actor,str(assignment_id),data)
    response.status_code=201 if created else 200
    return result
