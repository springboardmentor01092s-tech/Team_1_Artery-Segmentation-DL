"""Authenticated upload-only real-volume research QC; never persists or infers lesions."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.core.config import settings
from app.core.dependencies import require_roles
from app.core.roles import Role
from app.models import User
from app.schemas.real_volume_research import RealVolumeResearchResponse
from app.services.real_volume_research import MAX_REAL_VOXELS, RealVolumeResearchError, analyze_nifti_pair
from app.services.volume_ingestion import VolumeIngestionError, validate_nifti_extension, validate_nifti_file

router = APIRouter(prefix="/experimental-stenosis", tags=["Experimental real-volume research"])
ResearchUser = Annotated[User, Depends(require_roles(Role.ADMIN, Role.DATA_SCIENTIST, Role.RESEARCHER))]
_MAX_UPLOAD = 512 * 1024 * 1024


async def _copy_bounded(upload: UploadFile) -> tuple[Path, str]:
    try:
        extension = validate_nifti_extension(upload.filename or "")
    except VolumeIngestionError:
        raise HTTPException(422, "Only .nii and .nii.gz NIfTI uploads are supported.") from None
    max_file = min(_MAX_UPLOAD, settings.MAX_VOLUME_COMPRESSED_MB * 1024 * 1024) if extension == ".nii.gz" else min(
        settings.MAX_VOLUME_UNCOMPRESSED_FILE_MB * 1024 * 1024, settings.MAX_VOLUME_UNCOMPRESSED_MB * 1024 * 1024)
    descriptor, name = tempfile.mkstemp(prefix="vascuai-real-research-", suffix=extension)
    path = Path(name)
    size = 0
    try:
        with os.fdopen(descriptor, "wb") as target:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > max_file:
                    raise HTTPException(413, "A research volume exceeds the configured per-file upload limit.")
                target.write(chunk)
        if size == 0:
            raise HTTPException(422, "Research volume upload is empty.")
        try:
            validate_nifti_file(
                path, extension,
                max_uncompressed_bytes=settings.MAX_VOLUME_UNCOMPRESSED_MB * 1024 * 1024,
                max_voxels=min(settings.VASCULAI_MODEL_MAX_VOXELS, MAX_REAL_VOXELS),
            )
        except VolumeIngestionError as exc:
            raise HTTPException(422, str(exc)) from None
        return path, extension
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()


@router.post("/real-volume/analyze", response_model=RealVolumeResearchResponse,
             operation_id="analyze_real_volume_research_upload")
async def analyze_real_volume(
    current_user: ResearchUser,
    ct_volume: UploadFile = File(...),
    vessel_mask: UploadFile = File(...),
):
    """Validate one local CT/mask pair and return ephemeral topology/QC evidence.

    Uploaded masks are never trusted to be lumen masks. No patient/case ID,
    model checkpoint, database write or clinical output is accepted here.
    """
    ct_path: Path | None = None
    mask_path: Path | None = None
    try:
        ct_path, _ = await _copy_bounded(ct_volume)
        mask_path, _ = await _copy_bounded(vessel_mask)
        try:
            result = analyze_nifti_pair(ct_path, mask_path)
        except RealVolumeResearchError as exc:
            raise HTTPException(422, f"Real-volume research input rejected: {exc}") from None
        except (OSError, ValueError, RuntimeError, MemoryError, OverflowError):
            raise HTTPException(422, "Real-volume research could not safely read this CT/mask pair.") from None
        return RealVolumeResearchResponse.model_validate(result)
    finally:
        for path in (ct_path, mask_path):
            if path is not None:
                path.unlink(missing_ok=True)
