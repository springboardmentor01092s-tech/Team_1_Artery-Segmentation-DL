from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator


class CaseReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    segmentation_result_id: UUID
    outcome: Literal["accepted_for_research", "changes_requested"]
    note: str | None = Field(default=None, max_length=1000)
    acknowledge_research_only: StrictBool

    @field_validator("note")
    @classmethod
    def trim_note(cls, value):
        return (value.strip() or None) if value is not None else None

    @model_validator(mode="after")
    def require_acknowledgement(self):
        if not self.acknowledge_research_only:
            raise ValueError("Research-only acknowledgement is required")
        if self.outcome == "changes_requested" and not self.note:
            raise ValueError("Explain the requested changes without patient identifiers")
        return self


class RunEvidence(BaseModel):
    segmentation_result_id: str
    created_at: datetime
    source_sha256: str
    checkpoint_sha256: str
    mask_sha256: str
    probabilities_sha256: str
    threshold: float


class ResearchReview(BaseModel):
    id: str
    case_id: int
    segmentation_result_id: str
    reviewer_id: int
    reviewer_role: str
    reviewed_at: datetime
    outcome: Literal["accepted_for_research", "changes_requested"]
    note: str | None
    source_sha256: str
    checkpoint_sha256: str
    mask_sha256: str
    probabilities_sha256: str
    threshold: float
    current: bool
    scope: Literal["research_workflow_v1"]


class ModelAnalysisState(BaseModel):
    available: bool
    reason: str | None
    run: RunEvidence | None


class CaseWorkflowResponse(BaseModel):
    case_id: int
    case_status: Literal["pending", "awaiting_review", "complete", "changes_requested"]
    model_analysis: ModelAnalysisState
    review: ResearchReview | None
    review_history: list[ResearchReview]
    review_requires_new_run: bool
    research_only: Literal[True]
    clinical_validation: Literal[False]
