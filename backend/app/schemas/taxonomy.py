from pydantic import BaseModel, Field


class TaxonomyOptionItem(BaseModel):
    value: str
    is_approved: bool
    source: str


class TaxonomyFieldItem(BaseModel):
    field_key: str
    label_cn: str
    value_type: str
    dimension: str
    sort_order: int
    options: list[TaxonomyOptionItem]


class TaxonomyResponse(BaseModel):
    version: str
    fields: list[TaxonomyFieldItem]


class SubmitTaxonomyValueRequest(BaseModel):
    field_key: str = Field(..., examples=["style_tags"])
    proposed_value: str = Field(..., examples=["多巴胺"])
    submitted_by: str | None = Field(default=None, examples=["merchant-001"])


class SubmitTaxonomyValueResponse(BaseModel):
    submission_id: str
    field_key: str
    proposed_value: str
    is_approved: bool
    status: str


class TaxonomySubmissionItem(BaseModel):
    submission_id: str
    field_key: str
    proposed_value: str
    submitted_by: str | None = None
    is_approved: bool
    created_at: str


class ApproveSubmissionRequest(BaseModel):
    is_approved: bool = True
