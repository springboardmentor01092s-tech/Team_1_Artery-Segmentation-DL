"""Adjudication records reference human reviews; they do not calculate labels."""
from typing import Annotated, Literal
from pydantic import Field, StrictBool, StrictInt, StrictStr, model_validator
from app.schemas.annotation_draft import StrictModel, Identifier, Hash

Reason = Annotated[StrictStr, Field(min_length=1, max_length=2000)]

class AssignAdjudicator(StrictModel):
    reviewer_id: Annotated[StrictInt, Field(gt=0, le=2147483647)]
    credential_id: Identifier
    expected_source_sha256: Hash

class Correspondence(StrictModel):
    id: Identifier
    r1_lesion_ids: Annotated[list[Identifier], Field(max_length=100)]
    r2_lesion_ids: Annotated[list[Identifier], Field(max_length=100)]
    relation: Literal['matched', 'only_r1', 'only_r2', 'uncertain']
    reason: Reason
    @model_validator(mode='after')
    def membership(self):
        if not self.reason.strip() or not self.r1_lesion_ids and not self.r2_lesion_ids:
            raise ValueError('Correspondence requires a reason and lesion references')
        if self.relation == 'matched' and (not self.r1_lesion_ids or not self.r2_lesion_ids):
            raise ValueError('Matched correspondence requires both readers')
        if self.relation == 'only_r1' and (not self.r1_lesion_ids or self.r2_lesion_ids):
            raise ValueError('R1-only correspondence contradicts references')
        if self.relation == 'only_r2' and (not self.r2_lesion_ids or self.r1_lesion_ids):
            raise ValueError('R2-only correspondence contradicts references')
        return self

class Resolution(StrictModel):
    correspondence_id: Identifier
    field: Literal['lesion_presence', 'artery_segment', 'location_boundaries', 'minimum_diameter', 'reference_diameter', 'measurement_method']
    decision: Literal['agreement', 'prefer_r1', 'prefer_r2', 'unresolved']
    reason: Reason

class AdjudicationDocument(StrictModel):
    schema_version: Literal['review-adjudication/0.1']
    assignment_id: Identifier
    source_sha256: Hash
    protocol_version: Annotated[StrictStr, Field(min_length=1, max_length=128)]
    r1_submission_sha256: Hash
    r2_submission_sha256: Hash
    outcome: Literal['not_assessed', 'agreement', 'resolved_disagreement', 'unresolved']
    reason: Reason
    correspondences: Annotated[list[Correspondence], Field(max_length=200)]
    resolutions: Annotated[list[Resolution], Field(max_length=1200)]
    clinical_gate_authorized: StrictBool
    training_release_authorized: StrictBool
    @model_validator(mode='after')
    def no_release(self):
        if self.clinical_gate_authorized is not False or self.training_release_authorized is not False or not self.reason.strip():
            raise ValueError('Unverified adjudication requires a reason and both release flags false')
        return self

class SaveAdjudication(StrictModel):
    document: AdjudicationDocument
    expected_revision: Annotated[StrictInt, Field(ge=0, le=2147483646)]

class FinalizeAdjudication(StrictModel):
    expected_revision: Annotated[StrictInt, Field(ge=1, le=2147483646)]
    expected_document_sha256: Hash
    acknowledge_unverified: StrictBool
    @model_validator(mode='after')
    def explicit_acknowledgement(self):
        if self.acknowledge_unverified is not True:
            raise ValueError('Explicit acknowledgement of unverified status is required')
        return self
