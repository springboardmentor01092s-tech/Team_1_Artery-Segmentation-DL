"""Versioned addenda for an already immutable unverified reader submission."""
from typing import Annotated
from pydantic import Field, StrictBool, StrictInt, StrictStr, model_validator
from app.schemas.annotation_draft import Hash, StrictModel
from app.schemas.review_annotation import ReviewAnnotation


class CreateReviewAmendment(StrictModel):
    document: ReviewAnnotation
    reason: Annotated[StrictStr, Field(min_length=1, max_length=2000)]
    expected_revision: Annotated[StrictInt, Field(ge=0, le=99)]
    expected_previous_sha256: Hash | None
    expected_submission_sha256: Hash
    acknowledge_unverified: StrictBool

    @model_validator(mode='after')
    def explicit_unverified_addendum(self):
        if not self.reason.strip() or self.acknowledge_unverified is not True:
            raise ValueError('A reason and explicit unverified amendment acknowledgement are required')
        if (self.expected_revision == 0) != (self.expected_previous_sha256 is None):
            raise ValueError('Amendment revision and previous hash do not match')
        return self
