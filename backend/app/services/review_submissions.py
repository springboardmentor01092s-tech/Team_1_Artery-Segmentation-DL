from datetime import datetime,timezone
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select
from app.models.review_assignment import ReviewAssignment
from app.models.review_annotation import ReviewAnnotationDraft,ReviewAnnotationVersion
from app.models.review_submission import IndependentReviewSubmission
from app.services import review_assignments as assignments,review_annotations as annotations
from app.services.audit import record_event
from app.services.source_fingerprint import file_version

def write_lock(db,assignment_id):
    db.execute(select(ReviewAssignment.id).where(ReviewAssignment.id==assignment_id).with_for_update()).one()

def checked_payload(record):
    if (not isinstance(record.payload,dict) or not isinstance(record.payload.get('document'),dict)
            or annotations.content_hash(record.payload)!=record.record_sha256 or annotations.content_hash(record.payload['document'])!=record.document_sha256):
        raise HTTPException(409,'Immutable review integrity verification failed')
    if record.payload.get('clinical_gate_authorized') is not False or record.payload.get('training_release_authorized') is not False:
        raise HTTPException(409,'Immutable review authorization invalid')
    return record.payload

def read(db,actor,assignment_id):
    row,study=assignments.own_assignment(db,actor,assignment_id)
    record=db.scalar(select(IndependentReviewSubmission).where(IndependentReviewSubmission.assignment_id==row.id,
        IndependentReviewSubmission.owner_id==actor.id))
    current=True
    try:assignments.verify_assigned_source(db,study)
    except HTTPException:current=False
    result=dict(exists=record is not None,submission=checked_payload(record) if record else None,
        record_sha256=record.record_sha256 if record else None,source_current=current,**assignments.no_release())
    db.commit();return result

def submit(db,actor,assignment_id,data):
    row,study=assignments.own_assignment(db,actor,assignment_id);write_lock(db,row.id)
    existing=db.scalar(select(IndependentReviewSubmission).where(IndependentReviewSubmission.assignment_id==row.id))
    if existing:
        payload=checked_payload(existing)
        if existing.owner_id!=actor.id or payload['annotation_revision']!=data.expected_revision or existing.document_sha256!=data.expected_document_sha256:
            raise HTTPException(409,'A different immutable review is already submitted; amendments require a separate versioned process')
        result=dict(submission=payload,record_sha256=existing.record_sha256,**assignments.no_release());db.commit();return result,False
    _,_,path,version,_=assignments.verify_assigned_source(db,study)
    draft=db.get(ReviewAnnotationDraft,row.id)
    if draft is None or draft.revision!=data.expected_revision:raise HTTPException(409,'Save and reload the current annotation revision before submission')
    document=annotations.validate_binding(draft.document,row,study);digest=annotations.content_hash(document)
    history=db.scalar(select(ReviewAnnotationVersion).where(ReviewAnnotationVersion.assignment_id==row.id,
        ReviewAnnotationVersion.owner_id==actor.id,ReviewAnnotationVersion.revision==draft.revision))
    if history is None or history.content_sha256!=digest or annotations.content_hash(history.document)!=digest or digest!=data.expected_document_sha256:
        raise HTTPException(409,'Annotation version or hash changed before submission')
    key=str(uuid4())
    payload=dict(schema_version='independent-review-submission/0.1',id=key,assignment_id=row.id,reviewer_id=actor.id,
        case_id=study.case_id,source=study.source_json,geometry_identity={'version':'ct-geometry/1.0','sha256':study.geometry_sha256},
        protocol_version=study.protocol_version,annotation_version_id=history.id,annotation_revision=draft.revision,
        document_sha256=digest,document=document,submitted_at=datetime.now(timezone.utc).isoformat(),
        status='submitted_unverified_abstention' if document['case_disposition'] in ['not_assessed','ungradable'] else 'submitted_unverified',
        source_verified_at_submission=True,**assignments.no_release())
    record=IndependentReviewSubmission(id=key,assignment_id=row.id,owner_id=actor.id,version_id=history.id,
        document_sha256=digest,record_sha256=annotations.content_hash(payload),payload=payload,
        clinical_gate_authorized=False,training_release_authorized=False)
    db.add(record);db.flush()
    if file_version(path)!=version:raise HTTPException(409,'CT source changed during submission')
    result=dict(submission=payload,record_sha256=record.record_sha256,**assignments.no_release())
    record_event(db,'review.independent_submitted',actor.id,study.case_id);db.commit();return result,True
