"""Original CT and account-private preparation only; no expert-label release."""
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, or_, select, text, update

from app.core.config import settings
from app.models import AuditEvent, CaseReview, SegmentationResult, User
from app.models.annotation_draft import AnnotationDraft
from app.models.review_assignment import ReviewStudy, ReviewAssignment, ReviewNoteDraft
from app.schemas.annotation_draft import validate_native_geometry
from app.services.annotation_drafts import case_snapshot, locked_actor
from app.services.audit import record_event
from app.services.source_fingerprint import file_version, source_sha256
from app.services.volume_ingestion import validate_nifti_file


def no_release():
    return dict(clinical_gate_authorized=False, training_release_authorized=False,
                reader_independence_verified=False, qualification_verified=False)


def original_source(case):
    root = Path(settings.UPLOAD_DIR).resolve()
    folder = root / "volumes"
    source = root / (case.volume_path or "")
    try:
        if (not case.volume_path or case.modality not in {"CTA", "CT Angiography"}
                or folder.is_symlink() or source.is_symlink() or source.resolve().parent != folder.resolve()
                or not source.is_file() or source.stat().st_size == 0):
            raise ValueError()
        version = file_version(source)
        digest = source_sha256(source)
        compressed = source.name.lower().endswith(".nii.gz")
        props = validate_nifti_file(source, ".nii.gz" if compressed else ".nii",
            max_uncompressed_bytes=settings.MAX_VOLUME_UNCOMPRESSED_MB*1024*1024,
            max_voxels=settings.MAX_VOLUME_VOXELS)
        affine = [list(props.affine_flat[i:i+4]) for i in range(0, 16, 4)]
        if props.ndim != 3 or props.xyzt_units & 7 != 2 or not (props.qform_code or props.sform_code):raise ValueError()
        validate_native_geometry(list(props.shape), affine, "mm")
        if file_version(source) != version:raise ValueError()
        geometry = dict(shape=list(props.shape), affine=affine, units="mm")
        identity = hashlib.sha256(json.dumps({"version": "ct-geometry/1.0", **geometry},
            sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        return dict(case_id=case.id, source_sha256=digest, **geometry), identity, source, version, compressed
    except (OSError, ValueError, TypeError):
        raise HTTPException(409, "Original CT source is missing, changed, unsupported or unverifiable.") from None


def coordinator(db, actor):
    locked_actor(db, actor)
    if db.scalar(select(User.role).where(User.id == actor.id)) != "Admin":
        raise HTTPException(403, "Only an unassigned Admin coordinator may assign readers")
    if db.scalar(select(ReviewAssignment.id).where(ReviewAssignment.reviewer_id == actor.id).limit(1)):
        raise HTTPException(403, "An assigned reader cannot act as coordinator")


def source_preview(db, actor, case_id):
    coordinator(db, actor)
    case = case_snapshot(db, case_id)
    source, geometry, _, _, _ = original_source(case)
    record_event(db, "review.coordinator_source_read", actor.id, case_id)
    db.commit()
    return dict(case_id=case_id, source=source, geometry_identity={"version": "ct-geometry/1.0", "sha256": geometry}, **no_release())


def known_exposure(db, user_id, case_id):
    # Case discovery can reveal notes/status; absence of logs still does not
    # establish absence of outside knowledge or validate a reader's identity.
    audited = db.scalar(select(AuditEvent.id).where(AuditEvent.actor_id == user_id,
        or_(AuditEvent.action.in_(["case.list_read", "patient.list_read", "review.prior_workspace_access"]),
            AuditEvent.action.like("evaluation.%"), AuditEvent.action.like("model.%"),
            (AuditEvent.resource_id == case_id) & or_(AuditEvent.action.like("case.%"),
                AuditEvent.action.like("annotation.%"), AuditEvent.action.like("stenosis.%"), AuditEvent.action.like("reference.%"))))
        .limit(1))
    return bool(audited or db.scalar(select(AnnotationDraft.id).where(AnnotationDraft.owner_id == user_id, AnnotationDraft.case_id == case_id).limit(1))
                or db.scalar(select(CaseReview.id).where(CaseReview.reviewer_id == user_id, CaseReview.case_id == case_id).limit(1))
                or db.scalar(select(SegmentationResult.id).where(SegmentationResult.created_by == user_id, SegmentationResult.case_id == case_id).limit(1)))


def assign(db, actor, data):
    coordinator(db, actor)
    if actor.id in {data.r1_user_id, data.r2_user_id}:
        raise HTTPException(409, "The coordinator cannot also be an independent reader")
    # Drain earlier requests, including response streaming, before checking
    # exposure and atomically enabling mode. Stable ordering avoids lock cycles.
    if db.bind.dialect.name == "postgresql":
        for user_id in sorted([data.r1_user_id, data.r2_user_id]):
            db.execute(text("SELECT pg_advisory_xact_lock(1447121731, :actor)"), {"actor": user_id})
    users = db.execute(select(User.id, User.role, User.is_active).where(User.id.in_([data.r1_user_id, data.r2_user_id]))
                       .order_by(User.id).with_for_update()).all()
    if len(users) != 2 or any(row.role != "Clinician" or not row.is_active for row in users):
        raise HTTPException(409, "Two distinct active Clinician accounts are required; Admins cannot be blinded readers")
    case = case_snapshot(db, data.case_id)
    if any(known_exposure(db, row.id, case.id) for row in users):
        raise HTTPException(409, "A selected account has known prior case or AI exposure. Do not relabel it as a blinded reading.")
    source, geometry, path, version, _ = original_source(case)
    if source["source_sha256"] != data.expected_ct_sha256:
        raise HTTPException(409, "CT identity changed; inspect the current source before assignment")
    study = ReviewStudy(id=str(uuid4()), case_id=case.id, patient_id=case.patient_id, coordinator_id=actor.id,
                        protocol_version=data.protocol_version, source_volume_path=case.volume_path,
                        source_json=source, geometry_sha256=geometry,
                        clinical_gate_authorized=False, training_release_authorized=False)
    db.add(study);db.flush()
    rows = [ReviewAssignment(id=str(uuid4()), study_id=study.id, reviewer_id=user_id, slot=slot)
            for slot, user_id in [("R1", data.r1_user_id), ("R2", data.r2_user_id)]]
    db.add_all(rows);db.flush()
    if file_version(path) != version:raise HTTPException(409, "Source changed during assignment")
    result = dict(id=study.id, case_id=case.id, protocol_version=study.protocol_version, source=source,
        assignments=[dict(id=row.id, slot=row.slot, reviewer_id=row.reviewer_id) for row in rows], **no_release())
    record_event(db, "review.readers_assigned", actor.id, case.id);db.commit()
    return result


def own_assignment(db, actor, assignment_id):
    locked_actor(db, actor)
    value = db.execute(select(ReviewAssignment, ReviewStudy).join(ReviewStudy, ReviewStudy.id == ReviewAssignment.study_id)
        .where(ReviewAssignment.id == assignment_id, ReviewAssignment.reviewer_id == actor.id)).one_or_none()
    if value is None:raise HTTPException(404, "Review assignment not found")
    return value


def assignment_view(row, study):
    return dict(id=row.id, reviewer_id=row.reviewer_id, slot=row.slot, case_id=study.case_id, protocol_version=study.protocol_version,
                source=study.source_json, geometry_identity={"version": "ct-geometry/1.0", "sha256": study.geometry_sha256},
                review_mode="original_ct_only", **no_release())


def list_own(db, actor, limit, offset):
    locked_actor(db, actor)
    rows = db.execute(select(ReviewAssignment, ReviewStudy).join(ReviewStudy, ReviewStudy.id == ReviewAssignment.study_id)
        .where(ReviewAssignment.reviewer_id == actor.id).order_by(ReviewStudy.created_at.desc(), ReviewAssignment.id)
        .offset(offset).limit(limit+1)).all()
    result = dict(items=[assignment_view(a, s) for a, s in rows[:limit]], limit=limit, offset=offset,
        next_offset=offset+limit if len(rows)>limit and offset+limit<=1_000_000 else None,
        offset_limit_reached=len(rows)>limit and offset+limit>1_000_000, **no_release())
    db.commit();return result


def verify_assigned_source(db, study):
    case = case_snapshot(db, study.case_id)
    evidence = original_source(case)
    if (case.patient_id != study.patient_id or case.volume_path != study.source_volume_path
            or evidence[0] != study.source_json or evidence[1] != study.geometry_sha256):
        raise HTTPException(409, "Assignment source changed; no replacement CT or AI output is substituted")
    return evidence


def detail(db, actor, assignment_id):
    row, study = own_assignment(db, actor, assignment_id)
    current, reason = True, None
    try:verify_assigned_source(db, study)
    except HTTPException:current, reason = False, "Bound original CT is unavailable or changed."
    result = dict(**assignment_view(row, study), source_current=current, source_unavailable_reason=reason)
    db.commit();return result


def note_view(row, study, note):
    return dict(schema_version="ct-review-note/0.1", assignment_id=row.id, owner_id=row.reviewer_id, case_id=study.case_id,
        protocol_version=study.protocol_version, source=study.source_json,
        revision=note.revision if note else 0, notes=note.notes if note else "",
        exists=note is not None, status="unverified_draft", **no_release())


def get_note(db, actor, assignment_id):
    row, study = own_assignment(db, actor, assignment_id)
    note = db.get(ReviewNoteDraft, row.id)
    result = note_view(row, study, note)
    db.commit();return result


def note_for_save(db, assignment_id):
    return db.get(ReviewNoteDraft, assignment_id)


def save_note(db, actor, assignment_id, data):
    row, study = own_assignment(db, actor, assignment_id)
    _, _, path, version, _ = verify_assigned_source(db, study)
    note = note_for_save(db, row.id)
    if data.expected_revision == 0 and note is None:
        note = ReviewNoteDraft(assignment_id=row.id, owner_id=actor.id, notes=data.notes, revision=1,
                               clinical_gate_authorized=False, training_release_authorized=False)
        db.add(note);db.flush();created = True
    else:
        created = False
        if note is None or data.expected_revision < 1:
            raise HTTPException(409, "Review note revision conflict")
        result = db.execute(update(ReviewNoteDraft).where(ReviewNoteDraft.assignment_id == row.id,
            ReviewNoteDraft.owner_id == actor.id, ReviewNoteDraft.revision == data.expected_revision)
            .values(notes=data.notes, revision=data.expected_revision+1, updated_at=func.now())
            .execution_options(synchronize_session=False))
        if result.rowcount != 1:raise HTTPException(409, "Review note revision conflict")
        db.refresh(note)
    if file_version(path) != version:raise HTTPException(409, "Source changed during save")
    result = note_view(row, study, note)
    record_event(db, "review.private_note_saved", actor.id, study.case_id);db.commit()
    return result, created
