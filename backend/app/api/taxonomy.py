from fastapi import APIRouter, HTTPException, Query

from app.schemas.taxonomy import (
    ApproveSubmissionRequest,
    SubmitTaxonomyValueRequest,
    SubmitTaxonomyValueResponse,
    TaxonomyResponse,
    TaxonomySubmissionItem,
)
from app.services.taxonomy_store import (
    list_taxonomy,
    list_taxonomy_submissions,
    set_submission_approved,
    submit_taxonomy_value,
)
from app.services.business_db import search_taxonomy_options

router = APIRouter()


@router.get("/taxonomy/options")
def get_taxonomy_options(
    field_key: str = Query(..., min_length=1),
    q: str = Query(default="", description="模糊搜索关键词"),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[dict]:
    """按字段+关键词模糊搜索已审批的标签值"""
    return search_taxonomy_options(field_key=field_key, query=q, limit=limit)


@router.get("/taxonomy", response_model=TaxonomyResponse)
def get_taxonomy(
    include_pending: bool = Query(
        default=False,
        description="为 true 时选项列表包含待审核的用户提交标签",
    ),
) -> TaxonomyResponse:
    data = list_taxonomy(include_unapproved=include_pending)
    return TaxonomyResponse(**data)


@router.post("/taxonomy/submissions", response_model=SubmitTaxonomyValueResponse)
def create_taxonomy_submission(
    request: SubmitTaxonomyValueRequest,
) -> SubmitTaxonomyValueResponse:
    try:
        result = submit_taxonomy_value(
            field_key=request.field_key,
            proposed_value=request.proposed_value,
            submitted_by=request.submitted_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SubmitTaxonomyValueResponse(**result)


@router.get("/taxonomy/submissions", response_model=list[TaxonomySubmissionItem])
def get_taxonomy_submissions(
    pending_only: bool = Query(default=True),
) -> list[TaxonomySubmissionItem]:
    if pending_only:
        rows = list_taxonomy_submissions(approved=False)
    else:
        rows = list_taxonomy_submissions(approved=None)
    return [TaxonomySubmissionItem(**row) for row in rows]


@router.patch("/taxonomy/submissions/{submission_id}", response_model=TaxonomySubmissionItem)
def patch_taxonomy_submission(
    submission_id: str,
    request: ApproveSubmissionRequest,
) -> TaxonomySubmissionItem:
    try:
        result = set_submission_approved(submission_id, request.is_approved)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    rows = list_taxonomy_submissions(approved=None)
    row = next((item for item in rows if item["submission_id"] == submission_id), None)
    if not row:
        return TaxonomySubmissionItem(
            submission_id=result["submission_id"],
            field_key=result["field_key"],
            proposed_value=result["proposed_value"],
            is_approved=result["is_approved"],
            created_at="",
        )
    return TaxonomySubmissionItem(**row)
