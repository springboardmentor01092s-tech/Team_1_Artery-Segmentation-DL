"""Current research workflow evidence, never a clinical capability gate."""
import math
import re
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from app.core.config import settings
from app.models import CaseReview, SegmentationResult
from app.services.source_fingerprint import file_version, source_sha256

FINGERPRINT_FIELDS = ("source_sha256", "checkpoint_sha256", "mask_sha256", "probabilities_sha256", "threshold")


def model_evidence(db, case):
    runs = db.scalars(select(SegmentationResult).where(SegmentationResult.case_id == case.id)
                      .order_by(SegmentationResult.created_at.desc(), SegmentationResult.id.desc()).limit(2)).all()
    if not runs:
        return None, "No saved segmentation run."
    if len(runs) == 2 and runs[0].created_at == runs[1].created_at:
        return None, "The latest saved run order is ambiguous; generate a new run before review."
    latest = runs[0]
    if not case.volume_path or case.modality not in {"CTA", "CT Angiography"}:
        return None, "A current CT volume and confirmed CT modality are required."
    metadata = latest.metadata_json
    if not isinstance(metadata, dict):
        return None, "The saved run has no verifiable provenance."
    if latest.source_volume_path != case.volume_path:
        return None, "The saved run belongs to a replaced input; run segmentation again."
    if any(not isinstance(metadata.get(k), str) or not re.fullmatch(r"[0-9a-f]{64}", metadata[k])
           for k in ("source_sha256", "checkpoint_sha256")):
        return None, "The saved run has incomplete source/checkpoint provenance."
    threshold = metadata.get("threshold")
    if type(threshold) not in {int, float} or not math.isfinite(threshold) or not 0 <= threshold <= 1:
        return None, "The saved run has no valid recorded threshold."
    try:
        if str(UUID(latest.id)) != latest.id:
            raise ValueError()
        uploads = Path(settings.UPLOAD_DIR).resolve()
        source = uploads / case.volume_path
        outputs = Path(settings.OUTPUT_DIR).resolve() / "segmentations"
        directory = outputs / latest.id
        files = [source, directory / "prediction_mask.nii.gz", directory / "probabilities.nii.gz"]
        if (uploads / "volumes").is_symlink() or source.is_symlink() or source.resolve().parent != (uploads / "volumes").resolve():
            raise ValueError()
        if outputs.is_symlink() or directory.is_symlink() or directory.resolve().parent != outputs.resolve():
            raise ValueError()
        if any(f.is_symlink() or not f.is_file() or f.stat().st_size == 0 for f in files):
            raise ValueError()
        versions = [file_version(f) for f in files]
        hashes = [source_sha256(f) for f in files]
        if versions != [file_version(f) for f in files]:
            return None, "Source or outputs changed while checking workflow evidence."
        if hashes[0] != metadata["source_sha256"]:
            return None, "The saved run is stale: input bytes changed."
    except (OSError, ValueError):
        return None, "Source or saved output files are unavailable or unverifiable."
    return {"segmentation_result_id": latest.id, "created_at": latest.created_at,
            "source_sha256": hashes[0], "checkpoint_sha256": metadata["checkpoint_sha256"],
            "mask_sha256": hashes[1], "probabilities_sha256": hashes[2], "threshold": threshold}, None


def review_matches(review, evidence):
    return bool(evidence and review.segmentation_result_id == evidence["segmentation_result_id"]
                and all(getattr(review, key) == evidence[key] for key in FINGERPRINT_FIELDS))


def review_record(review, evidence):
    return {key: getattr(review, key) for key in (
        "id", "case_id", "segmentation_result_id", "reviewer_id", "reviewer_role", "reviewed_at",
        "outcome", "note", *FINGERPRINT_FIELDS)} | {"current": review_matches(review, evidence), "scope": "research_workflow_v1"}


def workflow_state(db, case):
    evidence, reason = model_evidence(db, case)
    history = db.scalars(select(CaseReview).where(CaseReview.case_id == case.id)
                         .order_by(CaseReview.reviewed_at.desc(), CaseReview.id.desc()).limit(20)).all()
    # A current run is looked up independently of the bounded history page.
    review = db.scalar(select(CaseReview).where(CaseReview.segmentation_result_id == evidence["segmentation_result_id"])) if evidence else None
    current = review if review and review_matches(review, evidence) else None
    state = "pending" if not evidence else "awaiting_review"
    if current:
        state = "complete" if current.outcome == "accepted_for_research" else "changes_requested"
    return {"case_id": case.id, "case_status": state, "model_analysis": {"available": evidence is not None,
            "reason": reason, "run": evidence}, "review": review_record(current, evidence) if current else None,
            "review_history": [review_record(r, evidence) for r in history],
            "review_requires_new_run": bool(review and not current),
            "research_only": True, "clinical_validation": False}
