from typing import Annotated

from pydantic import Field, StrictBool, StrictInt, StrictStr, model_validator

from app.schemas.annotation_draft import Hash, StrictModel


class AssignReaders(StrictModel):
    case_id: Annotated[StrictInt, Field(gt=0, le=2147483647)]
    r1_user_id: Annotated[StrictInt, Field(gt=0)]
    r2_user_id: Annotated[StrictInt, Field(gt=0)]
    expected_ct_sha256: Hash
    protocol_version: Annotated[StrictStr, Field(min_length=1, max_length=128)]
    acknowledge_unverified: StrictBool

    @model_validator(mode="after")
    def distinct(self):
        if self.r1_user_id == self.r2_user_id or not self.protocol_version.strip() or self.acknowledge_unverified is not True:
            raise ValueError("Two distinct readers, protocol version and unverified acknowledgement are required")
        return self


class SaveReviewNote(StrictModel):
    notes: Annotated[StrictStr, Field(max_length=4000)]
    expected_revision: Annotated[StrictInt, Field(ge=0, le=2147483646)]
    clinical_gate_authorized: StrictBool
    training_release_authorized: StrictBool

    @model_validator(mode="after")
    def no_release(self):
        if self.clinical_gate_authorized is not False or self.training_release_authorized is not False:
            raise ValueError("Clinical and training release remain unauthorized")
        try:self.notes.encode("utf-8")
        except UnicodeEncodeError:raise ValueError("Notes must be valid Unicode") from None
        return self
