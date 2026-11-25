"""Manual CT-only reader preparation; never clinical ground truth or release."""
from typing import Annotated, Literal
from pydantic import AfterValidator, Field, StrictBool, StrictInt, StrictStr, model_validator
from app.schemas.annotation_draft import StrictModel, Hash, Identifier, DraftLesion, Number, validate_native_geometry, POINT_FIELDS, utf16_limit

class OriginalCtSource(StrictModel):
    case_id: Annotated[StrictInt,Field(gt=0,le=2147483647)]
    source_sha256: Hash
    shape: Annotated[list[StrictInt],Field(min_length=3,max_length=3)]
    affine: Annotated[list[list[Number]],Field(min_length=4,max_length=4)]
    units: Literal['mm']
    @model_validator(mode='after')
    def geometry(self):
        validate_native_geometry(self.shape,self.affine,self.units);return self

class ReaderLesion(DraftLesion):
    measurement_method: Annotated[StrictStr,Field(max_length=500),AfterValidator(utf16_limit(500))]
    measurement_evidence: Annotated[StrictStr,Field(max_length=2000),AfterValidator(utf16_limit(2000))]
    @model_validator(mode='after')
    def explicit_measurement_support(self):
        if self.minimum_lumen_diameter_mm is not None or self.adjacent_reference_diameter_mm is not None:
            if not self.measurement_method.strip() or not self.measurement_evidence.strip():
                raise ValueError('Manual diameter entries require explicit method and evidence')
        for value,start,end in [(self.minimum_lumen_diameter_mm,self.minimum_caliper_start_ijk,self.minimum_caliper_end_ijk),
                                (self.adjacent_reference_diameter_mm,self.reference_caliper_start_ijk,self.reference_caliper_end_ijk)]:
            if value is not None and (start is None or end is None):
                raise ValueError('Manual diameter entries require source-bound measurement endpoints')
        return self

class ReviewAnnotation(StrictModel):
    schema_version: Literal['independent-lesion-review/0.1']
    assignment_id: Identifier
    source: OriginalCtSource
    protocol_version: Annotated[StrictStr,Field(min_length=1,max_length=128)]
    status: Literal['unverified_draft']
    label_origin: Literal['manual_independent_reader_unverified']
    clinical_gate_authorized: StrictBool
    training_release_authorized: StrictBool
    reader_qualification_verified: StrictBool
    reader_independence_verified: StrictBool
    case_disposition: Literal['not_assessed','lesions_proposed','no_lesion_reported','ungradable']
    case_unavailable_reason: Annotated[StrictStr,Field(max_length=2000),AfterValidator(utf16_limit(2000))]
    lesions: Annotated[list[ReaderLesion],Field(max_length=100)]
    @model_validator(mode='after')
    def source_bound_unverified(self):
        if any(getattr(self,k) is not False for k in ['clinical_gate_authorized','training_release_authorized','reader_qualification_verified','reader_independence_verified']):
            raise ValueError('All clinical/training/qualification/independence authorizations remain false')
        if not self.protocol_version.strip():raise ValueError('Protocol version is required')
        if self.case_disposition in {'not_assessed','ungradable'} and not self.case_unavailable_reason.strip():
            raise ValueError('Unassessed or ungradable review requires a reason')
        if self.case_disposition=='no_lesion_reported' and self.lesions or self.case_disposition=='lesions_proposed' and not self.lesions:
            raise ValueError('Case disposition contradicts proposed lesion rows')
        ids=set()
        for row in self.lesions:
            if row.percentage_narrowing is not None or row.severity_category is not None:
                raise ValueError('Percentage and severity labels remain unavailable without an approved expert protocol')
            if row.draft_id in ids:raise ValueError('Duplicate lesion identifier')
            ids.add(row.draft_id)
            for key in POINT_FIELDS:
                point=getattr(row,key)
                if point is not None and any(n<0 or n>self.source.shape[i]-1 for i,n in enumerate(point)):
                    raise ValueError('Landmark is outside the original native CT grid')
        return self

class SaveReviewAnnotation(StrictModel):
    document: ReviewAnnotation
    expected_revision: Annotated[StrictInt,Field(ge=0,le=2147483646)]

class SubmitReview(StrictModel):
    expected_revision: Annotated[StrictInt,Field(ge=1,le=2147483647)]
    expected_document_sha256: Hash
    acknowledge_unverified: StrictBool
    @model_validator(mode='after')
    def explicit_submission(self):
        if self.acknowledge_unverified is not True:raise ValueError('Explicit unverified immutable submission acknowledgement is required')
        return self
