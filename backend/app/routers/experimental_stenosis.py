"""Authenticated, non-persistent synthetic-only stenosis research workflow."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.core.config import settings
from app.core.dependencies import require_roles
from app.core.roles import Role
from app.models import User
from app.schemas.experimental_stenosis import (
    ExperimentalAnalysisRequest, ExperimentalAnalysisResponse, ExperimentalSampleRequest,
    ExperimentalSampleResponse, ExperimentalStatusResponse,
)
from app.services.synthetic_stenosis_ml import (
    DEFAULT_SHAPE, NOTICE, analyze_synthetic_phantom,
    generate_phantom, load_verified_checkpoint,
)

router = APIRouter(prefix="/experimental-stenosis", tags=["Experimental synthetic stenosis research"])
ResearchUser = Annotated[User, Depends(require_roles(Role.ADMIN, Role.DATA_SCIENTIST, Role.RESEARCHER))]


def checkpoint():
    path = settings.VASCULAI_SYNTHETIC_STENOSIS_CHECKPOINT
    digest = settings.VASCULAI_SYNTHETIC_STENOSIS_CHECKPOINT_SHA256
    if not path or not digest:
        raise HTTPException(503, "Synthetic research checkpoint is not configured")
    try:
        return load_verified_checkpoint(path, digest)
    except ValueError:
        raise HTTPException(503, "Verified synthetic research checkpoint unavailable") from None


@router.get("/status", response_model=ExperimentalStatusResponse)
def status(current_user: ResearchUser):
    try:
        checkpoint()
    except HTTPException as exc:
        return ExperimentalStatusResponse(available=False, reason=exc.detail,
            scope="synthetic_generated_phantoms_only", clinical_gate_authorized=False,
            training_release_authorized=False)
    return ExperimentalStatusResponse(available=True, reason=None,
        scope="synthetic_generated_phantoms_only", clinical_gate_authorized=False,
        training_release_authorized=False)


@router.post("/samples", response_model=ExperimentalSampleResponse)
def create_sample(request: ExperimentalSampleRequest, current_user: ResearchUser):
    sample = generate_phantom(request.sample_id, request.synthetic_class_id, request.seed)
    middle = DEFAULT_SHAPE[2] // 2
    # Do not expose synthetic target parameters or lesion truth in the browser
    # sample contract; this route is the input to the analysis workflow.
    public_provenance = {key: sample["provenance"][key] for key in (
        "source", "generator_version", "sample_id", "seed", "volume_sha256", "notice")}
    return ExperimentalSampleResponse(
        schema_version="synthetic-stenosis-sample/0.2", sample_id=sample["sample_id"],
        shape=DEFAULT_SHAPE,
        middle_slice_k=middle, middle_slice=sample["volume"][:, :, middle].astype(float).tolist(),
        provenance=public_provenance, notice=NOTICE,
        clinical_validation=False, clinical_gate_authorized=False, training_release_authorized=False,
    )


@router.post("/analyze", response_model=ExperimentalAnalysisResponse)
def analyze(request: ExperimentalAnalysisRequest, current_user: ResearchUser):
    # Never accepts a client-supplied volume/path/case ID. Server regenerates the
    # complete synthetic sample from a bounded seed/class contract.
    sample = generate_phantom(request.sample_id, request.synthetic_class_id, request.seed)
    model, model_metadata, checkpoint_sha = checkpoint()
    if model_metadata.get("test_metrics", {}).get("scope") != "synthetic_test_split_only":
        raise HTTPException(503, "Synthetic model metadata failed validation")
    try:
        result = analyze_synthetic_phantom(
            sample, model, checkpoint_sha,
            severity_thresholds=request.provisional_severity_thresholds_percent,
        )
        return ExperimentalAnalysisResponse.model_validate(result)
    except (ValueError, RuntimeError, OverflowError):
        raise HTTPException(422, "Synthetic experimental analysis could not be completed") from None
