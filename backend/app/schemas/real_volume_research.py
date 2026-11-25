"""Non-persistent real-volume research QC response contract."""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class RealVolumeResearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["real-volume-research/0.1"]
    status: Literal["profile_only", "abstained"]
    notice: str
    provenance: dict[str, Any]
    geometry: dict[str, Any]
    segmentation: dict[str, Any]
    centerline: dict[str, Any]
    candidates: list[dict[str, Any]]
    candidate_status: Literal["unavailable_mask_semantics_unverified"]
    measurements: dict[str, Any]
    clinical_validation: Literal[False]
    clinical_gate_authorized: Literal[False]
    training_release_authorized: Literal[False]
