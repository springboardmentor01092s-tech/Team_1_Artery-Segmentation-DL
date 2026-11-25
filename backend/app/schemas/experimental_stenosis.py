"""Contracts for the separate synthetic-only experimental stenosis workbench."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from app.services.synthetic_stenosis_ml import (
    DEFAULT_RESEARCH_SEVERITY_THRESHOLDS,
    validate_research_severity_thresholds,
)

_GROUND_TRUTH_OUTPUT_KEYS = {
    "class_label", "synthetic_class_label", "synthetic_geometry_ground_truth",
    "true_label", "ground_truth_label",
}


def _reject_ground_truth_output(value: Any) -> Any:
    if isinstance(value, dict):
        if _GROUND_TRUTH_OUTPUT_KEYS.intersection(value):
            raise ValueError("synthetic ground truth is benchmark-only and cannot be returned")
        for nested in value.values():
            _reject_ground_truth_output(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _reject_ground_truth_output(nested)
    return value


class ExperimentalSampleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    sample_id: StrictInt = Field(ge=0, le=1_000_000)
    synthetic_class_id: StrictInt = Field(ge=0, le=4)
    seed: StrictInt = Field(ge=0, le=2_147_483_647)


class ExperimentalAnalysisRequest(ExperimentalSampleRequest):
    provisional_severity_thresholds_percent: list[float] = Field(
        default_factory=lambda: list(DEFAULT_RESEARCH_SEVERITY_THRESHOLDS), min_length=4, max_length=4,
    )

    @field_validator("provisional_severity_thresholds_percent")
    @classmethod
    def validate_provisional_thresholds(cls, value):
        try:
            return list(validate_research_severity_thresholds(value))
        except ValueError:
            raise ValueError("provide four strictly increasing research thresholds between 0 and 100") from None


class ExperimentalSampleResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["synthetic-stenosis-sample/0.2"]
    sample_id: int
    shape: tuple[int, int, int]
    middle_slice_k: int
    middle_slice: list[list[float]]
    provenance: dict[str, Any]
    notice: str
    clinical_validation: Literal[False]
    clinical_gate_authorized: Literal[False]
    training_release_authorized: Literal[False]

    @model_validator(mode="after")
    def no_ground_truth(self):
        _reject_ground_truth_output(self.model_dump())
        return self


class ExperimentalAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["experimental-stenosis-analysis/0.3"]
    generated_at: datetime
    status: Literal["completed_synthetic_research_only"]
    notice: str
    provenance: dict[str, Any]
    geometry_analysis: dict[str, Any]
    model: dict[str, Any]
    explainability: dict[str, Any]
    clinical_validation: Literal[False]
    clinical_gate_authorized: Literal[False]
    training_release_authorized: Literal[False]

    @model_validator(mode="after")
    def no_ground_truth(self):
        _reject_ground_truth_output(self.model_dump())
        return self


class ExperimentalStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    available: bool
    reason: str | None = None
    scope: Literal["synthetic_generated_phantoms_only"]
    clinical_gate_authorized: Literal[False]
    training_release_authorized: Literal[False]
