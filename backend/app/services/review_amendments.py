"""Append-only, reviewer-private addenda; the submitted parent is never replaced."""
from datetime import datetime, timezone
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select
from app.models.review_submission import IndependentReviewSubmission, ReviewSubmissionAmendment
from app.models.review_adjudication import AdjudicationAssignment
from app.services import review_annotations, review_assignments, review_submissions
from app.services.audit import record_event
from app.services.source_fingerprint import file_version

MAX_AMENDMENTS = 100


def _checked(row, assignment, study, parent):
    payload = row.payload
    if (not isinstance(payload, dict) or not isinstance(payload.get('document'), dict)
            or review_annotations.content_hash(payload) != row.record_sha256
            or review_annotations.content_hash(payload['document']) != row.document_sha256
            or row.assignment_id != assignment.id or row.owner_id != assignment.reviewer_id
            or row.submission_id != parent.id or row.parent_submission_sha256 != parent.record_sha256
            or payload.get('clinical_gate_authorized') is not False
            or payload.get('training_release_authorized') is not False
            or payload.get('assignment_id') != assignment.id
            or payload.get('reviewer_id') != assignment.reviewer_id
            or payload.get('parent_submission_sha256') != parent.record_sha256
            or payload.get('revision') != row.revision):
        raise HTTPException(409, 'Amendment integrity or parent binding verification failed')
    document = review_annotations.validate_binding(payload['document'], assignment, study)
    if document != payload['document']:
        raise HTTPException(409, 'Amendment document binding verification failed')
    return dict(id=row.id, revision=row.revision, previous_id=row.previous_id,
        previous_sha256=row.previous_sha256, parent_submission_sha256=row.parent_submission_sha256,
        document_sha256=row.document_sha256, record_sha256=row.record_sha256,
        amendment=payload, created_at=row.created_at.isoformat() if row.created_at else None)


def _chain(db, assignment, study, parent):
    rows = db.scalars(select(ReviewSubmissionAmendment).where(
        ReviewSubmissionAmendment.assignment_id == assignment.id,
        ReviewSubmissionAmendment.owner_id == assignment.reviewer_id).order_by(ReviewSubmissionAmendment.revision)).all()
    if len(rows) > MAX_AMENDMENTS:
        raise HTTPException(409, 'Amendment history exceeds the supported verification bound')
    result=[]; previous_id=None; previous_hash=None
    for revision, row in enumerate(rows, 1):
        if (row.revision != revision or row.previous_id != previous_id or row.previous_sha256 != previous_hash
                or row.parent_submission_sha256 != parent.record_sha256):
            raise HTTPException(409, 'Amendment history chain is broken')
        result.append(_checked(row, assignment, study, parent))
        previous_id=row.id; previous_hash=row.record_sha256
    return rows, result


def read(db, actor, assignment_id):
    assignment, study = review_assignments.own_assignment(db, actor, assignment_id)
    parent=db.scalar(select(IndependentReviewSubmission).where(
        IndependentReviewSubmission.assignment_id == assignment.id,
        IndependentReviewSubmission.owner_id == actor.id))
    if parent is None:
        raise HTTPException(409, 'An immutable independent submission is required before adding an amendment')
    review_submissions.checked_payload(parent)
    _, items = _chain(db, assignment, study, parent)
    try:
        review_assignments.verify_assigned_source(db, study); source_current=True
    except HTTPException:
        source_current=False
    result=dict(schema_version='review-amendment-history/0.1', assignment_id=assignment.id,
        submission_id=parent.id, submission_sha256=parent.record_sha256, source_current=source_current,
        items=items, revision=len(items), latest_sha256=items[-1]['record_sha256'] if items else None,
        max_amendments=MAX_AMENDMENTS, clinical_gate_authorized=False,
        training_release_authorized=False)
    db.commit(); return result


def append(db, actor, assignment_id, data):
    assignment, study=review_assignments.own_assignment(db, actor, assignment_id)
    review_submissions.write_lock(db, assignment.id)
    parent=db.scalar(select(IndependentReviewSubmission).where(
        IndependentReviewSubmission.assignment_id == assignment.id,
        IndependentReviewSubmission.owner_id == actor.id))
    if parent is None:
        raise HTTPException(409, 'An immutable independent submission is required before adding an amendment')
    parent_payload=review_submissions.checked_payload(parent)
    rows, _ = _chain(db, assignment, study, parent)
    if (data.expected_submission_sha256 != parent.record_sha256
            or data.expected_revision != len(rows)
            or data.expected_previous_sha256 != (rows[-1].record_sha256 if rows else None)):
        raise HTTPException(409, 'Amendment parent or revision is stale; reload the immutable history')
    if len(rows) >= MAX_AMENDMENTS:
        raise HTTPException(409, 'The amendment history limit has been reached')
    if db.scalar(select(AdjudicationAssignment.id).where(
            AdjudicationAssignment.study_id == study.id).limit(1)):
        raise HTTPException(409, 'Amendments are closed after a third reviewer has been assigned')
    evidence=review_assignments.verify_assigned_source(db, study)
    document=review_annotations.validate_binding(data.document.model_dump(mode='json'), assignment, study)
    revision=len(rows)+1; previous=rows[-1] if rows else None; key=str(uuid4())
    payload=dict(schema_version='review-submission-amendment/0.1', id=key,
        assignment_id=assignment.id, submission_id=parent.id, reviewer_id=actor.id,
        revision=revision, previous_id=previous.id if previous else None,
        previous_sha256=previous.record_sha256 if previous else None,
        parent_submission_sha256=parent.record_sha256,
        parent_annotation_revision=parent_payload['annotation_revision'],
        source=study.source_json, geometry_identity={'version':'ct-geometry/1.0','sha256':study.geometry_sha256},
        protocol_version=study.protocol_version, reason=data.reason.strip(),
        document_sha256=review_annotations.content_hash(document), document=document,
        status='unverified_addendum_original_submission_unchanged',
        recorded_at=datetime.now(timezone.utc).isoformat(),
        clinical_gate_authorized=False, training_release_authorized=False)
    record_sha=review_annotations.content_hash(payload)
    row=ReviewSubmissionAmendment(id=key,assignment_id=assignment.id,submission_id=parent.id,
        owner_id=actor.id,revision=revision,previous_id=payload['previous_id'],
        previous_sha256=payload['previous_sha256'],parent_submission_sha256=parent.record_sha256,
        document_sha256=payload['document_sha256'],record_sha256=record_sha,payload=payload,
        clinical_gate_authorized=False,training_release_authorized=False)
    db.add(row);db.flush()
    if file_version(evidence[2]) != evidence[3]:
        raise HTTPException(409, 'Original CT changed during amendment')
    result=_checked(row, assignment, study, parent)
    record_event(db,'review.submission_amendment_added',actor.id,study.case_id)
    db.commit()
    return dict(**result, clinical_gate_authorized=False, training_release_authorized=False), True
