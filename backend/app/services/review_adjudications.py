"""Human third-reader decisions, append-only and never a training/clinical release."""
from datetime import datetime, timezone
import re
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import aliased
from app.models import User
from app.models.review_assignment import ReviewAssignment, ReviewStudy
from app.models.review_submission import IndependentReviewSubmission, ReviewSubmissionAmendment
from app.models.review_adjudication import ReviewerCredential, AdjudicationAssignment, AdjudicationVersion
from app.services import review_assignments as readers, review_submissions, review_annotations
from app.services.annotation_drafts import locked_actor
from app.services.audit import record_event
from app.services.source_fingerprint import file_version
from app.services.review_coverage import review_coverage

SCOPE = 'coronary-cta-lesion-adjudication'
HISTORY_LIMIT = 50
_PYTHON_WHITESPACE='\t\n\v\f\r\x1c\x1d\x1e\x1f \x85\xa0\u1680'+''.join(chr(i) for i in range(0x2000,0x200b))+'\u2028\u2029\u202f\u205f\u3000'


def eligible_credential(verifier,now):
    """Same evidence prerequisites as qualified(), applied before SQL pagination."""
    return (verifier.role=='Admin',ReviewerCredential.revoked.is_(False),
        ReviewerCredential.verified_at<=now,ReviewerCredential.valid_until>now,
        ReviewerCredential.scope==SCOPE,
        ReviewerCredential.verified_by!=ReviewerCredential.reviewer_id,
        # Explicit Unicode set matches str.strip(), independent of DB locale.
        ReviewerCredential.evidence_reference.regexp_match('[^'+_PYTHON_WHITESPACE+']'),
        ReviewerCredential.evidence_sha256.regexp_match('^[a-f0-9]{64}$'))

def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def qualified(db, credential_id, reviewer_id):
    row = db.scalar(select(ReviewerCredential).where(ReviewerCredential.id == credential_id,
        ReviewerCredential.reviewer_id == reviewer_id).with_for_update(read=True).execution_options(populate_existing=True))
    now = datetime.now(timezone.utc)
    verifier = db.scalar(select(User).where(User.id == row.verified_by)) if row else None
    if (row is None or verifier is None or verifier.role != 'Admin' or row.revoked or row.scope != SCOPE or not row.evidence_reference.strip()
            or not re.fullmatch(r'[a-f0-9]{64}',row.evidence_sha256) or row.verified_by == reviewer_id
            or utc(row.verified_at) > now or utc(row.valid_until) <= now):
        raise HTTPException(409, 'Separately verified, current clinical reviewer credentials are required; no self-attestation is accepted')
    return row


def coordinator_catalogue(db, actor):
    readers.coordinator(db, actor)
    studies = db.scalars(select(ReviewStudy).order_by(ReviewStudy.created_at.desc(), ReviewStudy.id).limit(100)).all()
    now = datetime.now(timezone.utc)
    verifier=aliased(User)
    credentials = db.execute(select(ReviewerCredential, User).join(User, User.id == ReviewerCredential.reviewer_id)
        .join(verifier,verifier.id==ReviewerCredential.verified_by)
        .where(User.is_active, User.role == 'Clinician', *eligible_credential(verifier,now),
               ~select(ReviewAssignment.id).where(ReviewAssignment.reviewer_id == User.id).exists())
        .order_by(ReviewerCredential.id).limit(100)).all()
    result = dict(studies=[dict(id=s.id, case_id=s.case_id, protocol_version=s.protocol_version,
        source_sha256=s.source_json['source_sha256']) for s in studies],
        credentials=[dict(id=c.id, reviewer_id=u.id, name=u.full_name, valid_until=c.valid_until) for c, u in credentials],
        catalogue_limit=100, **readers.no_release())
    db.commit(); return result


def parents(db, assignment):
    result = []
    for key, digest in [(assignment.r1_submission_id, assignment.r1_sha256), (assignment.r2_submission_id, assignment.r2_sha256)]:
        row = db.get(IndependentReviewSubmission, key)
        if row is None or row.record_sha256 != digest:
            raise HTTPException(409, 'Frozen parent review hash changed')
        payload = review_submissions.checked_payload(row)
        result.append(dict(record_sha256=digest, submission=payload))
    return result


def assign(db, actor, study_id, data):
    readers.coordinator(db, actor)
    if actor.id == data.reviewer_id:
        raise HTTPException(409, 'The coordinator cannot adjudicate')
    if db.bind.dialect.name == 'postgresql':
        db.execute(text('SELECT pg_advisory_xact_lock(1447121731, :actor)'), {'actor': data.reviewer_id})
    user = db.scalar(select(User).where(User.id == data.reviewer_id).with_for_update())
    if user is None or not user.is_active or user.role != 'Clinician' or db.scalar(select(ReviewAssignment.id).where(ReviewAssignment.reviewer_id == user.id).limit(1)):
        raise HTTPException(409, 'A separate active Clinician account is required')
    qualified(db, data.credential_id, user.id)
    study = db.get(ReviewStudy, study_id)
    if study is None: raise HTTPException(404, 'Review study not found')
    evidence = readers.verify_assigned_source(db, study)
    if data.expected_source_sha256 != study.source_json['source_sha256']:
        raise HTTPException(409, 'Source changed before adjudicator assignment')
    frozen = db.execute(select(ReviewAssignment.slot, IndependentReviewSubmission).join(IndependentReviewSubmission,
        IndependentReviewSubmission.assignment_id == ReviewAssignment.id).where(ReviewAssignment.study_id == study.id)).all()
    mapped = {slot: row for slot, row in frozen}
    if set(mapped) != {'R1', 'R2'}:
        raise HTTPException(409, 'Both independent reviews must be frozen before assignment')
    for row in mapped.values(): review_submissions.checked_payload(row)
    if db.scalar(select(ReviewSubmissionAmendment.id).where(
            ReviewSubmissionAmendment.submission_id.in_([mapped['R1'].id, mapped['R2'].id])).limit(1)):
        raise HTTPException(409, 'A reviewer amendment exists; the current adjudication contract cannot bind it safely')
    assignment = AdjudicationAssignment(id=str(uuid4()), study_id=study.id, reviewer_id=user.id, coordinator_id=actor.id,
        credential_id=data.credential_id, r1_submission_id=mapped['R1'].id, r2_submission_id=mapped['R2'].id,
        r1_sha256=mapped['R1'].record_sha256, r2_sha256=mapped['R2'].record_sha256)
    db.add(assignment); db.flush()
    if file_version(evidence[2]) != evidence[3]: raise HTTPException(409, 'CT changed during assignment')
    result = dict(id=assignment.id, case_id=study.case_id, **readers.no_release())
    record_event(db, 'review.adjudicator_assigned', actor.id, study.case_id); db.commit(); return result


def own(db, actor, key):
    locked_actor(db, actor)
    if actor.role != 'Clinician': raise HTTPException(403, 'A separately assigned Clinician adjudicator is required')
    value = db.execute(select(AdjudicationAssignment, ReviewStudy).join(ReviewStudy, ReviewStudy.id == AdjudicationAssignment.study_id)
        .where(AdjudicationAssignment.id == key, AdjudicationAssignment.reviewer_id == actor.id)).one_or_none()
    if value is None: raise HTTPException(404, 'Adjudication assignment not found')
    qualified(db, value[0].credential_id, actor.id)
    return value


def list_own(db, actor, limit, offset):
    locked_actor(db, actor)
    if actor.role != 'Clinician': raise HTTPException(403, 'A separately assigned Clinician adjudicator is required')
    now = datetime.now(timezone.utc)
    verifier=aliased(User)
    rows = db.execute(select(AdjudicationAssignment, ReviewStudy).join(ReviewStudy, ReviewStudy.id == AdjudicationAssignment.study_id)
        .join(ReviewerCredential, ReviewerCredential.id == AdjudicationAssignment.credential_id)
        .join(verifier,verifier.id==ReviewerCredential.verified_by)
        .where(AdjudicationAssignment.reviewer_id == actor.id,*eligible_credential(verifier,now))
        .order_by(AdjudicationAssignment.created_at.desc(), AdjudicationAssignment.id)
        .offset(offset).limit(limit + 1)).all()
    result = dict(items=[dict(id=a.id, case_id=s.case_id, protocol_version=s.protocol_version) for a, s in rows[:limit]],
        next_offset=offset + limit if len(rows) > limit and offset + limit <= 1_000_000 else None, **readers.no_release())
    db.commit(); return result


def latest(db, key):
    return db.scalar(select(AdjudicationVersion).where(AdjudicationVersion.assignment_id == key).order_by(AdjudicationVersion.revision.desc()).limit(1))


def checked(row):
    if (not isinstance(row.payload, dict) or not isinstance(row.payload.get('document'), dict)
            or review_annotations.content_hash(row.payload) != row.record_sha256
            or review_annotations.content_hash(row.payload['document']) != row.document_sha256):
        raise HTTPException(409, 'Adjudication history integrity verification failed')
    return dict(record=row.payload, record_sha256=row.record_sha256, document_sha256=row.document_sha256)


def detail(db, actor, key):
    assignment, study = own(db, actor, key)
    db.execute(select(AdjudicationAssignment.id).where(AdjudicationAssignment.id==key).with_for_update(read=True)).one()
    reviews = parents(db, assignment)
    current = True
    try: readers.verify_assigned_source(db, study)
    except HTTPException: current = False
    current_record = latest(db, key)
    if current_record: checked(current_record)
    # Do not load every historical 2 MiB document on each page visit. Recent
    # chain metadata is bounded in SQL; any old immutable version is retrievable
    # separately through the owner/credential-checked version route.
    versions = list(reversed(db.execute(select(AdjudicationVersion.revision, AdjudicationVersion.final,
        AdjudicationVersion.record_sha256, AdjudicationVersion.previous_sha256).where(AdjudicationVersion.assignment_id == key)
        .order_by(AdjudicationVersion.revision.desc()).limit(HISTORY_LIMIT)).all()))
    first = versions[0].revision if versions else 1
    previous = versions[0].previous_sha256 if first > 1 else None
    for index, row in enumerate(versions, first):
        if row.previous_sha256 != previous or row.revision != index:
            raise HTTPException(409, 'Broken adjudication history chain')
        previous = row.record_sha256
    result = dict(id=key, reviewer_id=actor.id, case_id=study.case_id, source=study.source_json,
        protocol_version=study.protocol_version, parents=reviews, source_current=current,
        documentation_coverage=review_coverage(study.source_json,study.protocol_version,reviews),
        current=checked(current_record) if current_record else None, history_first_revision=first, history_truncated=first>1,
        history=[dict(revision=r.revision, final=r.final, record_sha256=r.record_sha256, previous_sha256=r.previous_sha256) for r in versions],
        **readers.no_release())
    db.commit(); return result


def version(db, actor, key, revision):
    assignment, _ = own(db, actor, key); parents(db, assignment)
    row = db.scalar(select(AdjudicationVersion).where(AdjudicationVersion.assignment_id == key,
        AdjudicationVersion.owner_id == actor.id, AdjudicationVersion.revision == revision))
    if row is None: raise HTTPException(404, 'Adjudication version not found')
    result = dict(**checked(row), **readers.no_release()); db.commit(); return result


def validate_document(data, assignment, study, reviews, final=False):
    doc = data.model_dump(mode='json')
    if (doc['assignment_id'] != assignment.id or doc['source_sha256'] != study.source_json['source_sha256']
            or doc['protocol_version'] != study.protocol_version or doc['r1_submission_sha256'] != assignment.r1_sha256
            or doc['r2_submission_sha256'] != assignment.r2_sha256):
        raise HTTPException(409, 'Adjudication document source or parent bindings mismatch')
    allowed = [{v['draft_id'] for v in r['submission']['document']['lesions']} for r in reviews]
    used = [set(), set()]; ids = set()
    for row in doc['correspondences']:
        if row['id'] in ids: raise HTTPException(422, 'Duplicate correspondence')
        ids.add(row['id'])
        for i, field in enumerate(['r1_lesion_ids', 'r2_lesion_ids']):
            for key in row[field]:
                if key not in allowed[i] or key in used[i]: raise HTTPException(422, 'Unknown or duplicated parent lesion reference')
                used[i].add(key)
    decisions = set()
    groups = {
        'artery_segment': ['artery','segment','segment_convention'],
        'location_boundaries': ['center_ijk','proximal_boundary_ijk','distal_boundary_ijk'],
        'minimum_diameter': ['minimum_lumen_diameter_mm','minimum_caliper_start_ijk','minimum_caliper_end_ijk'],
        'reference_diameter': ['adjacent_reference_diameter_mm','reference_caliper_start_ijk','reference_caliper_end_ijk','reference_selection'],
        'measurement_method': ['measurement_method','measurement_evidence','unavailable_reason'],
    }
    lesions = [{v['draft_id']: v for v in r['submission']['document']['lesions']} for r in reviews]
    def same_field(correspondence, field):
        left = correspondence['r1_lesion_ids']; right = correspondence['r2_lesion_ids']
        if field == 'lesion_presence': return bool(left) == bool(right) and len(left) == len(right)
        # Many-to-many correspondence is not assumed to establish measurement
        # equality. A human must record preference or unresolved status.
        if len(left) != 1 or len(right) != 1: return False
        return all(lesions[0][left[0]][key] == lesions[1][right[0]][key] for key in groups[field])
    for row in doc['resolutions']:
        pair = row['correspondence_id'], row['field']
        if row['correspondence_id'] not in ids or pair in decisions or not row['reason'].strip():
            raise HTTPException(422, 'Invalid or duplicated discrepancy resolution')
        decisions.add(pair)
        match = next(c for c in doc['correspondences'] if c['id'] == row['correspondence_id'])
        if row['decision'] == 'prefer_r1' and not match['r1_lesion_ids'] or row['decision'] == 'prefer_r2' and not match['r2_lesion_ids']:
            raise HTTPException(422, 'Preferred reader has no referenced lesion')
        if row['decision'] == 'agreement' and not same_field(match, row['field']):
            raise HTTPException(422, 'Agreement contradicts the frozen field evidence')
    if final:
        if doc['outcome'] == 'not_assessed' or used != allowed:
            raise HTTPException(422, 'Final adjudication must account for every parent lesion and state an outcome')
        incomplete = any(r['submission']['document']['case_disposition'] in {'not_assessed', 'ungradable'} for r in reviews)
        if incomplete and doc['outcome'] != 'unresolved':
            raise HTTPException(422, 'Unassessed or ungradable parent reviews cannot establish agreement')
        if doc['outcome'] == 'agreement' and (
                reviews[0]['submission']['document']['case_disposition'] != reviews[1]['submission']['document']['case_disposition']
                or any(c['relation'] != 'matched' for c in doc['correspondences'])
                or any(r['decision'] != 'agreement' for r in doc['resolutions'])):
            raise HTTPException(422, 'Agreement contradicts unmatched lesions or discrepancy decisions')
        if doc['outcome'] != 'unresolved' and (any(c['relation'] == 'uncertain' for c in doc['correspondences'])
                or any(r['decision'] == 'unresolved' for r in doc['resolutions'])):
            raise HTTPException(422, 'Unresolved discrepancies contradict the declared outcome')
        if ids != {r['correspondence_id'] for r in doc['resolutions']}:
            raise HTTPException(422, 'Each correspondence needs an explicit resolution, including unresolved decisions')
        for match in doc['correspondences']:
            required = {'lesion_presence'}
            if match['r1_lesion_ids'] and match['r2_lesion_ids']:
                required |= {field for field in groups if not same_field(match, field)}
            present = {r['field'] for r in doc['resolutions'] if r['correspondence_id'] == match['id']}
            if not required <= present:
                raise HTTPException(422, 'Record explicit decisions for differing fields: '+', '.join(sorted(required-present)))
    return doc


def write_lock(db, key):
    db.execute(select(AdjudicationAssignment.id).where(AdjudicationAssignment.id == key).with_for_update()).one()


def append(db, actor, assignment, study, doc, previous, final):
    key = str(uuid4()); revision = previous.revision + 1 if previous else 1
    payload = dict(schema_version='review-adjudication-version/0.1', id=key, assignment_id=assignment.id,
        reviewer_id=actor.id, revision=revision, previous_id=previous.id if previous else None,
        previous_sha256=previous.record_sha256 if previous else None, document=doc,
        status='adjudicated_unverified' if final else 'unverified_adjudication_draft',
        recorded_at=datetime.now(timezone.utc).isoformat(), **readers.no_release())
    row = AdjudicationVersion(id=key, assignment_id=assignment.id, owner_id=actor.id, revision=revision,
        previous_id=payload['previous_id'], previous_sha256=payload['previous_sha256'],
        document_sha256=review_annotations.content_hash(doc), record_sha256=review_annotations.content_hash(payload),
        payload=payload, final=final, clinical_gate_authorized=False, training_release_authorized=False)
    db.add(row); db.flush()
    record_event(db, 'review.adjudication_frozen' if final else 'review.adjudication_saved', actor.id, study.case_id)
    return row


def save(db, actor, key, data):
    assignment, study = own(db, actor, key); write_lock(db, key)
    evidence = readers.verify_assigned_source(db, study); previous = latest(db, key)
    if previous: checked(previous)
    if (previous and previous.final) or data.expected_revision != (previous.revision if previous else 0):
        raise HTTPException(409, 'Adjudication revision is stale or already immutable')
    doc = validate_document(data.document, assignment, study, parents(db, assignment))
    row = append(db, actor, assignment, study, doc, previous, False)
    if file_version(evidence[2]) != evidence[3]: raise HTTPException(409, 'Source changed during save')
    result = dict(**checked(row), **readers.no_release()); db.commit(); return result


def finalize(db, actor, key, data):
    from app.schemas.review_adjudication import AdjudicationDocument
    assignment, study = own(db, actor, key); write_lock(db, key)
    evidence = readers.verify_assigned_source(db, study); previous = latest(db, key)
    if previous is None: raise HTTPException(409, 'Save a reviewed adjudication revision first')
    checked(previous)
    if previous.final:
        if previous.revision == data.expected_revision + 1 and previous.document_sha256 == data.expected_document_sha256:
            result = dict(**checked(previous), **readers.no_release()); db.commit(); return result, False
        raise HTTPException(409, 'Adjudication already immutable; amendments require a separate versioned process')
    if previous.revision != data.expected_revision or previous.document_sha256 != data.expected_document_sha256:
        raise HTTPException(409, 'Adjudication revision or hash changed')
    doc = validate_document(AdjudicationDocument.model_validate(previous.payload['document']), assignment, study, parents(db, assignment), True)
    row = append(db, actor, assignment, study, doc, previous, True)
    if file_version(evidence[2]) != evidence[3]: raise HTTPException(409, 'Source changed during finalization')
    result = dict(**checked(row), **readers.no_release()); db.commit(); return result, True
