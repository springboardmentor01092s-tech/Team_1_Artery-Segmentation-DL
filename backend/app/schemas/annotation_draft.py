"""Unverified local-document contract, shared with annotation-draft.js via parity tests.

Python does not execute client JavaScript. This is the server implementation of
the same Stage 1 validation policy, with independent authoritative source checks.
"""
import math
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr, model_validator

MAX_DRAFT_BYTES = 2 * 1024 * 1024
POINT_FIELDS = ("center_ijk", "proximal_boundary_ijk", "distal_boundary_ijk",
                "minimum_caliper_start_ijk", "minimum_caliper_end_ijk",
                "reference_caliper_start_ijk", "reference_caliper_end_ijk")
FALSE_FIELDS = ("reader_independence_verified", "clinical_validation", "training_eligible",
                "quantitative_gate_authorized", "clinical_gate_authorized", "training_release_authorized")
Number = StrictInt | StrictFloat
Point = Annotated[list[Number], Field(min_length=3, max_length=3)]
Hash = Annotated[StrictStr, Field(pattern=r"^[a-f0-9]{64}$")]
Identifier = Annotated[StrictStr, Field(pattern=r"(?i)^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$")]
def utf16_limit(maximum):
    def validate(value):
        if len(value.encode("utf-16-le", errors="surrogatepass"))//2 > maximum:
            raise ValueError("Annotation text exceeds the shared UTF-16 length bound")
        # Lone surrogates cannot safely be emitted as UTF-8 JSON by the API.
        try:value.encode("utf-8")
        except UnicodeEncodeError:raise ValueError("Annotation text must be valid Unicode") from None
        return value
    return validate


Text = Annotated[StrictStr, Field(max_length=1000), AfterValidator(utf16_limit(1000))]
ShortText = Annotated[StrictStr, Field(max_length=200), AfterValidator(utf16_limit(200))]
Reason = Annotated[StrictStr, Field(max_length=500), AfterValidator(utf16_limit(500))]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


def validate_native_geometry(shape, affine, units):
    """Stage 1 native geometry policy, also usable without a model/run identity."""
    if (units != "mm" or len(shape) != 3 or any(type(n) is not int or n < 1 for n in shape)
            or math.prod(shape) > 9007199254740991):
        raise ValueError("Invalid annotation dimensions or units")
    if len(affine) != 4 or any(len(row) != 4 or any(type(n) not in (int, float) or not math.isfinite(n) for n in row) for row in affine):
        raise ValueError("Invalid annotation affine")
    if affine[3] != [0, 0, 0, 1]:
        raise ValueError("Invalid homogeneous affine row")
    (u, v, w, _), (p, q, r, _), (s, t, k, _), _ = affine
    determinant = u*(q*k-r*t)-v*(p*k-r*s)+w*(p*t-q*s)
    scale = math.hypot(u, p, s)*math.hypot(v, q, t)*math.hypot(w, r, k)
    if not math.isfinite(determinant) or not math.isfinite(scale) or scale <= 0 or abs(determinant)/scale < 1e-8:
        raise ValueError("Singular or ill-conditioned annotation affine")


class AnnotationSource(StrictModel):
    case_id: Annotated[StrictInt, Field(gt=0, le=2147483647)]
    source_sha256: Hash
    segmentation_result_id: Identifier
    shape: Annotated[list[StrictInt], Field(min_length=3, max_length=3)]
    affine: Annotated[list[list[Number]], Field(min_length=4, max_length=4)]
    units: Literal["mm"]

    @model_validator(mode="after")
    def geometry(self):
        validate_native_geometry(self.shape, self.affine, self.units)
        return self


class DraftLesion(StrictModel):
    draft_id: Identifier
    artery: Literal["", "LM", "LAD", "LCx", "RCA", "graft", "other"]
    segment: ShortText
    segment_convention: ShortText
    center_ijk: Point | None
    proximal_boundary_ijk: Point | None
    distal_boundary_ijk: Point | None
    minimum_caliper_start_ijk: Point | None
    minimum_caliper_end_ijk: Point | None
    reference_caliper_start_ijk: Point | None
    reference_caliper_end_ijk: Point | None
    minimum_lumen_diameter_mm: Annotated[Number, Field(ge=0)] | None
    adjacent_reference_diameter_mm: Annotated[Number, Field(gt=0)] | None
    reference_selection: Reason
    percentage_narrowing: Annotated[Number, Field(ge=0, le=100)] | None
    percentage_basis: Reason
    severity_category: Literal["minimal", "mild", "moderate", "severe", "occluded", "ungradable"] | None
    unavailable_reason: Text
    notes: Text

    @model_validator(mode="after")
    def reasons(self):
        if (not self.unavailable_reason.strip()
                or self.adjacent_reference_diameter_mm is not None and not self.reference_selection.strip()
                or self.percentage_narrowing is not None and not self.percentage_basis.strip()):
            raise ValueError("Manual values and missing values require explicit reasons")
        return self


class AnnotationDocument(StrictModel):
    schema_version: Literal["lesion-annotation-workspace/0.1"]
    source: AnnotationSource
    status: Literal["unverified_local_draft"]
    label_origin: Literal["manual_reader_preparation_not_expert_ground_truth"]
    algorithm_exposure: Literal["predicted_segmentation_available_in_workspace"]
    reader_independence_verified: StrictBool
    clinical_validation: StrictBool
    training_eligible: StrictBool
    quantitative_gate_authorized: StrictBool
    clinical_gate_authorized: StrictBool
    training_release_authorized: StrictBool
    reviewer_reference: ShortText
    protocol_reference: Reason
    proposed_lesions: Annotated[list[DraftLesion], Field(max_length=100)]

    @model_validator(mode="after")
    def unverified(self):
        if any(getattr(self, key) is not False for key in FALSE_FIELDS):
            raise ValueError("Clinical, independence and training authorization must remain false")
        identifiers = [row.draft_id for row in self.proposed_lesions]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("Duplicate worksheet identifiers")
        for row in self.proposed_lesions:
            for key in POINT_FIELDS:
                point = getattr(row, key)
                if point is not None and any(not math.isfinite(n) or n < 0 or n > self.source.shape[i]-1 for i, n in enumerate(point)):
                    raise ValueError("Landmark outside the original CT grid")
        return self


class CreateDraft(StrictModel):
    document: AnnotationDocument


class UpdateDraft(CreateDraft):
    expected_revision: Annotated[StrictInt, Field(ge=1, le=2147483646)]


class DraftResponse(StrictModel):
    id: Identifier
    patient_id: StrictInt
    case_id: StrictInt
    owner_id: StrictInt
    revision: StrictInt
    status: Literal["unverified_server_draft"]
    source_current: StrictBool
    source_unavailable_reason: str | None
    geometry_identity: dict
    segmentation_provenance: dict
    document: AnnotationDocument
    clinical_gate_authorized: Literal[False]
    training_release_authorized: Literal[False]
    created_at: datetime
    updated_at: datetime


class DraftIndexItem(StrictModel):
    id: Identifier
    case_id: StrictInt
    owner_id: StrictInt
    revision: StrictInt
    segmentation_result_id: Identifier
    source_sha256: Hash
    status: Literal["unverified_server_draft"]
    updated_at: datetime
    clinical_gate_authorized: Literal[False]
    training_release_authorized: Literal[False]


class DraftIndex(StrictModel):
    items: list[DraftIndexItem]
    limit: StrictInt
    offset: StrictInt
    next_offset: int | None
    offset_limit_reached: StrictBool
