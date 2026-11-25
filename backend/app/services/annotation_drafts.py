"""Owner-only preparation drafts; never a clinical result, label or submission."""
import hashlib
import json
from pathlib import Path
import re
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import delete, func, select, update

from app.core.config import settings
from app.core.roles import CLINICAL_WRITERS
from app.models import Case, SegmentationResult, User
from app.models.annotation_draft import AnnotationDraft
from app.schemas.annotation_draft import AnnotationSource, MAX_DRAFT_BYTES
from app.services.audit import record_event
from app.services.source_fingerprint import file_version, source_sha256
from app.services.volume_ingestion import validate_nifti_file, VolumeIngestionError


def conflict(message="Draft source or provenance changed; refresh before saving."):
    raise HTTPException(409, message)


def locked_actor(db, actor):
    # FOR SHARE allows concurrent saves, but serializes role/session revocation.
    version = actor.token_version
    current = db.execute(select(User.id, User.role, User.is_active, User.token_version)
                         .where(User.id == actor.id).with_for_update(read=True)).one_or_none()
    if current is None or not current.is_active or current.token_version != version:
        raise HTTPException(401, "Invalid or expired access token")
    if current.role not in CLINICAL_WRITERS:
        raise HTTPException(403, "Clinician or Admin authoring permission is required")


def case_snapshot(db, case_id):
    # Existing case policy permits every authenticated case reader. No new grants.
    case = db.scalar(select(Case).where(Case.id == case_id).with_for_update(read=True)
                     .execution_options(populate_existing=True))
    if case is None:
        raise HTTPException(404, "Case not found")
    return case


def capture_evidence(db, case, run_id):
    run = db.scalar(select(SegmentationResult).where(SegmentationResult.id == run_id,
                    SegmentationResult.case_id == case.id).with_for_update(read=True))
    if run is None or not case.volume_path or run.source_volume_path != case.volume_path:
        conflict()
    metadata = run.metadata_json
    if not isinstance(metadata, dict) or not isinstance(metadata.get("checkpoint_sha256"), str) or not re.fullmatch(r"[a-f0-9]{64}", metadata["checkpoint_sha256"]):
        conflict("Saved run checkpoint provenance is unavailable.")
    threshold = metadata.get("threshold")
    if type(threshold) not in (int, float) or not 0 <= threshold <= 1:
        conflict("Saved run threshold provenance is unavailable.")
    uploads = Path(settings.UPLOAD_DIR).resolve()
    volumes = uploads / "volumes"
    source = uploads / case.volume_path
    outputs = Path(settings.OUTPUT_DIR).resolve() / "segmentations"
    directory = outputs / run.id
    paths = [source, directory / "prediction_mask.nii.gz", directory / "probabilities.nii.gz"]
    try:
        if (case.modality not in {"CTA", "CT Angiography"} or volumes.is_symlink() or source.is_symlink()
                or source.resolve().parent != volumes.resolve() or outputs.is_symlink() or directory.is_symlink()
                or directory.resolve().parent != outputs.resolve()
                or any(path.is_symlink() or not path.is_file() or path.stat().st_size == 0 for path in paths)):
            conflict("Source or saved artifacts are unavailable or unsafe.")
        versions = [file_version(path) for path in paths]
        hashes = [source_sha256(path) for path in paths]
        extension = ".nii.gz" if source.name.lower().endswith(".nii.gz") else ".nii"
        props = validate_nifti_file(source, extension,
            max_uncompressed_bytes=settings.MAX_VOLUME_UNCOMPRESSED_MB * 1024 * 1024,
            max_voxels=settings.MAX_VOLUME_VOXELS)
        if props.ndim != 3 or props.xyzt_units & 7 != 2 or not (props.sform_code or props.qform_code):
            conflict("An original 3D CT with explicit millimetre geometry is required.")
        affine = [list(props.affine_flat[i:i+4]) for i in range(0, 16, 4)]
        source_data = AnnotationSource(case_id=case.id, source_sha256=hashes[0], segmentation_result_id=run.id,
                                       shape=list(props.shape), affine=affine, units="mm").model_dump()
        if (metadata.get("source_sha256") != hashes[0] or metadata.get("shape") != source_data["shape"]
                or metadata.get("affine") != affine or metadata.get("xyzt_units", 0) & 7 != 2):
            conflict()
        unchanged_files(paths, versions)
    except (OSError, ValueError, TypeError, ValidationError, VolumeIngestionError):
        conflict("Source or saved artifacts cannot be verified.")
    geometry = {key: source_data[key] for key in ("shape", "affine", "units")}
    geometry_hash = hashlib.sha256(json.dumps({"version": "ct-geometry/1.0", **geometry},
        sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    provenance = dict(segmentation_result_id=run.id, checkpoint_sha256=metadata["checkpoint_sha256"],
                      mask_sha256=hashes[1], probabilities_sha256=hashes[2], threshold=threshold)
    return source_data, geometry_hash, provenance, paths, versions


def unchanged_files(paths, versions):
    if [file_version(path) for path in paths] != versions:
        conflict("Source or artifacts changed during draft validation.")


def owned_draft(db, case_id, draft_id, actor_id):
    row = db.scalar(select(AnnotationDraft).where(AnnotationDraft.id == draft_id,
                    AnnotationDraft.case_id == case_id, AnnotationDraft.owner_id == actor_id))
    if row is None:
        raise HTTPException(404, "Annotation draft not found")
    return row


def list_drafts(db, actor, case_id, run_id, limit, offset):
    locked_actor(db, actor)
    case_snapshot(db, case_id)
    statement = select(AnnotationDraft).where(AnnotationDraft.owner_id == actor.id,
                                              AnnotationDraft.case_id == case_id)
    if run_id is not None:
        statement = statement.where(AnnotationDraft.segmentation_result_id == run_id)
    # Authorization filtering precedes SQL pagination, including the sentinel.
    rows = db.scalars(statement.order_by(AnnotationDraft.updated_at.desc(), AnnotationDraft.id)
                      .offset(offset).limit(limit+1)).all()
    items = [dict(id=row.id, case_id=row.case_id, owner_id=row.owner_id, revision=row.revision,
                  segmentation_result_id=row.segmentation_result_id, source_sha256=row.source_json["source_sha256"],
                  status=row.status, updated_at=row.updated_at,
                  clinical_gate_authorized=False, training_release_authorized=False) for row in rows[:limit]]
    more = len(rows) > limit
    result = dict(items=items, limit=limit, offset=offset,
                  next_offset=offset+limit if more and offset+limit <= 1_000_000 else None,
                  offset_limit_reached=more and offset+limit > 1_000_000)
    record_event(db, "annotation.draft_list_read", actor.id, case_id)
    db.commit()
    return result


def checked_evidence(db, case, document, row=None):
    evidence = capture_evidence(db, case, document.source.segmentation_result_id)
    source, geometry, provenance, _, _ = evidence
    if document.source.model_dump() != source:
        conflict("Document CT hash, geometry or saved run does not match the stored source.")
    if row and (row.patient_id != case.patient_id or row.source_volume_path != case.volume_path
                or row.source_json != source or row.geometry_sha256 != geometry or row.segmentation_provenance != provenance):
        conflict()
    return evidence


def bounded_document(document):
    payload = document.model_dump()
    if len(json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()) > MAX_DRAFT_BYTES:
        raise HTTPException(413, "Annotation document exceeds 2 MiB")
    return payload


def envelope(row, current=True, reason=None):
    return dict(id=row.id, patient_id=row.patient_id, case_id=row.case_id, owner_id=row.owner_id,
                revision=row.revision, status=row.status, source_current=current, source_unavailable_reason=reason,
                geometry_identity={"version": "ct-geometry/1.0", "sha256": row.geometry_sha256},
                segmentation_provenance=row.segmentation_provenance, document=row.document,
                clinical_gate_authorized=False, training_release_authorized=False,
                created_at=row.created_at, updated_at=row.updated_at)


def create_draft(db, actor, case_id, document):
    locked_actor(db, actor)
    case = case_snapshot(db, case_id)
    evidence = checked_evidence(db, case, document)
    source, geometry, provenance, paths, versions = evidence
    row = AnnotationDraft(id=str(uuid4()), case_id=case.id, patient_id=case.patient_id, owner_id=actor.id,
                          segmentation_result_id=source["segmentation_result_id"], source_volume_path=case.volume_path,
                          source_json=source, geometry_sha256=geometry, segmentation_provenance=provenance,
                          document=bounded_document(document), clinical_gate_authorized=False, training_release_authorized=False)
    db.add(row)
    record_event(db, "annotation.draft_created", actor.id, case.id)
    db.flush()
    unchanged_files(paths, versions)
    result = envelope(row)
    db.commit()
    return result


def read_draft(db, actor, case_id, draft_id):
    locked_actor(db, actor)
    row = owned_draft(db, case_id, draft_id, actor.id)
    case = case_snapshot(db, case_id)
    current, reason = True, None
    try:
        from app.schemas.annotation_draft import AnnotationDocument
        checked_evidence(db, case, AnnotationDocument.model_validate(row.document), row)
    except (HTTPException, ValidationError):
        current, reason = False, "Bound source or saved run is stale, missing or unverifiable; saving is disabled."
    result = envelope(row, current, reason)
    record_event(db, "annotation.draft_read", actor.id, case_id)
    db.commit()
    return result


def update_draft(db, actor, case_id, draft_id, document, revision):
    locked_actor(db, actor)
    row = owned_draft(db, case_id, draft_id, actor.id)
    if row.revision != revision:
        conflict("Annotation draft revision conflict; retrieve the latest revision before saving.")
    case = case_snapshot(db, case_id)
    _, _, _, paths, versions = checked_evidence(db, case, document, row)
    result = db.execute(update(AnnotationDraft).where(AnnotationDraft.id == draft_id,
        AnnotationDraft.owner_id == actor.id, AnnotationDraft.case_id == case_id,
        AnnotationDraft.revision == revision, AnnotationDraft.status == "unverified_server_draft")
        .values(document=bounded_document(document), revision=revision+1, updated_at=func.now())
        .execution_options(synchronize_session=False))
    if result.rowcount != 1:
        db.rollback()
        conflict("Annotation draft revision conflict; retrieve the latest revision before saving.")
    record_event(db, "annotation.draft_updated", actor.id, case_id)
    unchanged_files(paths, versions)
    db.refresh(row)
    result = envelope(row)
    db.commit()
    return result


def delete_draft(db, actor, case_id, draft_id, revision):
    locked_actor(db, actor)
    owned_draft(db, case_id, draft_id, actor.id)
    result = db.execute(delete(AnnotationDraft).where(AnnotationDraft.id == draft_id,
        AnnotationDraft.owner_id == actor.id, AnnotationDraft.case_id == case_id,
        AnnotationDraft.revision == revision, AnnotationDraft.status == "unverified_server_draft")
        .execution_options(synchronize_session=False))
    if result.rowcount != 1:
        db.rollback()
        conflict("Annotation draft revision conflict; retrieve the latest revision before deleting.")
    record_event(db, "annotation.draft_deleted", actor.id, case_id)
    db.commit()
