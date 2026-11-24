from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Query, Path, Response
from app.routers.admin import Admin
from app.routers.cases import ClinicalWriter, DatabaseSession
from app.routers.review_assignments import call
from app.routers.segmentation import SourceSnapshotResponse, snapshot_source
from app.core.config import settings
from app.schemas.review_adjudication import AssignAdjudicator, SaveAdjudication, FinalizeAdjudication
from app.services import review_adjudications as service, review_assignments

router = APIRouter(tags=['Unverified third-reader adjudication'])

@router.get('/review-adjudication-catalogue')
def catalogue(response: Response, actor: Admin, db: DatabaseSession):
    return call(response, service.coordinator_catalogue, db, actor)

@router.post('/review-studies/{study_id}/adjudicator', status_code=201)
def assign(study_id: UUID, data: AssignAdjudicator, response: Response, actor: Admin, db: DatabaseSession):
    return call(response, service.assign, db, actor, str(study_id), data)

@router.get('/review-adjudications')
def own(response: Response, actor: ClinicalWriter, db: DatabaseSession,
        limit: Annotated[int, Query(ge=1, le=50)] = 20, offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0):
    return call(response, service.list_own, db, actor, limit, offset)

@router.get('/review-adjudications/{assignment_id}')
def detail(assignment_id: UUID, response: Response, actor: ClinicalWriter, db: DatabaseSession):
    return call(response, service.detail, db, actor, str(assignment_id))

@router.get('/review-adjudications/{assignment_id}/versions/{revision}')
def version(assignment_id: UUID, revision: Annotated[int, Path(ge=1,le=2147483647)], response: Response,
            actor: ClinicalWriter, db: DatabaseSession):
    return call(response, service.version, db, actor, str(assignment_id), revision)

@router.get('/review-adjudications/{assignment_id}/source')
def source(assignment_id: UUID, actor: ClinicalWriter, db: DatabaseSession):
    from fastapi import HTTPException
    _, study = service.own(db, actor, str(assignment_id))
    _, _, path, _, compressed = review_assignments.verify_assigned_source(db, study)
    try: snapshot = snapshot_source(path, study.source_json['source_sha256'], compressed,
        max_bytes=min(512,settings.MAX_VOLUME_COMPRESSED_MB if compressed else settings.MAX_VOLUME_UNCOMPRESSED_FILE_MB)*1024*1024)
    except (OSError, ValueError): raise HTTPException(409, 'Original CT snapshot could not be verified') from None
    try:
        db.commit(); return SourceSnapshotResponse(snapshot, compressed)
    except BaseException:
        snapshot.close(); raise

@router.put('/review-adjudications/{assignment_id}/draft')
def save(assignment_id: UUID, data: SaveAdjudication, response: Response, actor: ClinicalWriter, db: DatabaseSession):
    return call(response, service.save, db, actor, str(assignment_id), data)

@router.post('/review-adjudications/{assignment_id}/submit', status_code=201)
def finalize(assignment_id: UUID, data: FinalizeAdjudication, response: Response, actor: ClinicalWriter, db: DatabaseSession):
    result, created = call(response, service.finalize, db, actor, str(assignment_id), data)
    response.status_code = 201 if created else 200
    return result
