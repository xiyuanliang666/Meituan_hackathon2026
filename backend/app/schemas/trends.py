from typing import Any

from pydantic import BaseModel, Field


class UGCImportRequest(BaseModel):
    posts: list[dict[str, Any]]


class UGCImportResponse(BaseModel):
    imported_count: int
    updated_count: int
    total_count: int


class TrendRunCreateRequest(BaseModel):
    triggered_by: str = Field(default="manual")
    min_support: int = Field(default=2, ge=1, le=20)
    max_trends: int = Field(default=20, ge=1, le=100)


class TrendRunResponse(BaseModel):
    run_id: str
    triggered_by: str
    status: str
    total_posts: int = 0
    processed_posts: int = 0
    created_trends: int = 0
    error_message: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class TrendPipelineRunCreateRequest(BaseModel):
    triggered_by: str = Field(default="manual")
    input_json_path: str = Field(default="backend/mock_data/ugc_posts_from_links_clean.json")
    output_json_path: str = Field(default="backend/mock_data/ugc_posts_from_links_clean.json")
    raw_comments_file: str = Field(default="backend/mock_data/ugc_posts_from_links_clean_raw_comments.json")
    posts: list[dict[str, Any]] | None = None
    seed_links: list[str] | None = None
    user_data_dir: str = Field(default="backend/.playwright-xhs-profile")
    provider: str = Field(default="auto")
    limit: int | None = Field(default=None, ge=1, le=500)
    refresh_ttl_hours: int = Field(default=72, ge=0, le=720)
    only_missing: bool = True
    force_refresh: bool = False
    skip_comment_pipeline: bool = False
    comment_limit: int = Field(default=0, ge=0, le=1000)
    login_wait_seconds: int = Field(default=60, ge=0, le=600)
    min_support: int = Field(default=2, ge=1, le=20)
    max_trends: int = Field(default=20, ge=1, le=100)
    resume: bool = True
    from_start: bool = False
    force_summary: bool = False
    headless: bool = False
    auto_convert_to_draft: bool = False
    convert_limit: int = Field(default=3, ge=1, le=20)
    merchant_id: str = Field(default="demo_shop", min_length=1)
    use_trend_tags: bool = True


class TrendPipelineRunResponse(BaseModel):
    pipeline_run_id: str
    triggered_by: str
    status: str
    stage: str
    input_json_path: str
    output_json_path: str
    raw_comments_file: str
    provider: str
    total_posts: int = 0
    processed_posts: int = 0
    imported_posts: int = 0
    updated_posts: int = 0
    generated_trends: int = 0
    converted_drafts: int = 0
    linked_trend_run_id: str = ""
    auto_convert_to_draft: bool = False
    error_message: str = ""
    logs: list[dict[str, Any]] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class TrendListItem(BaseModel):
    trend_id: str
    core_style: str
    representative_image_url: str = ""
    style_source_image_url: str = ""
    keywords: list[str] = Field(default_factory=list)
    trend_score: float = 0
    confidence: float = 0
    life_cycle: str = "观察期"
    data_lifecycle: str = "recent"
    trend_lifecycle: str = "insufficient_history"
    reasoning_summary: str = ""
    status: str = "watch"
    push_status: str = "not_pushed"
    identified_at: str
    first_seen_at: str = ""
    last_seen_at: str = ""
    last_run_id: str = ""
    memory_status: str = "watching"
    score_history: list[dict[str, Any]] = Field(default_factory=list)
    signal_quality_distribution: dict[str, int] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    comment_signal_summary: dict[str, Any] = Field(default_factory=dict)
    supporting_post_ids: list[str] = Field(default_factory=list)


class TrendDetailResponse(TrendListItem):
    supporting_posts: list[dict[str, Any]] = Field(default_factory=list)


class TrendActionRequest(BaseModel):
    merchant_id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    note: str = ""


class TrendActionResponse(BaseModel):
    action_id: str
    merchant_id: str
    trend_id: str
    action: str
    note: str = ""
    draft_style_id: str = ""
    created_at: str


class TrendConvertToDraftRequest(BaseModel):
    merchant_id: str = Field(min_length=1)
    style_name: str | None = None
    use_trend_tags: bool = True
    note: str = ""


class DataHealthResponse(BaseModel):
    total_posts: int = 0
    classified: int = 0
    comments_done: int = 0
    fetch_failed: int = 0
    filtered_out: int = 0
    pending_classification: int = 0
    empty_content: int = 0
    zero_interaction: int = 0
    ready_for_trend_discovery: bool = False
    health: str = "needs_attention"


class CandidateTaxonomyTermItem(BaseModel):
    candidate_term: str
    normalized_form: str
    target_field: str
    frequency: int = 0
    variant_forms: list[str] = Field(default_factory=list)
    related_official_tags: list[str] = Field(default_factory=list)
    support_post_ids: list[str] = Field(default_factory=list)
    growth_rate_7d: float = 0.0
    discovered_run_id: str = ""
    status: str = "pending"
    created_at: str = ""
    updated_at: str = ""


class CandidateTaxonomyTermListResponse(BaseModel):
    terms: list[CandidateTaxonomyTermItem]


class CandidateTaxonomyTermUpdateRequest(BaseModel):
    status: str = Field(min_length=1)
    candidate_term: str | None = None
    normalized_form: str | None = None
    target_field: str | None = None


class TrendConvertToDraftResponse(BaseModel):
    trend_id: str
    style_id: str
    style_name: str
    image_url: str = ""
    status: str = "draft"
    review_status: str = "tag_ready"
    material_status: str = "ready"
    source: str = "trend_agent"
    source_trend_id: str = ""
    tags: dict[str, Any] = Field(default_factory=dict)


class TrendResolveCoverResponse(BaseModel):
    trend_id: str
    image_url: str = ""
    resolved: bool = False


class TrendPushToQueueRequest(BaseModel):
    merchant_id: str = "demo_shop"


class TrendPushToQueueResponse(BaseModel):
    trend_id: str
    push_id: str = ""
    pushed: bool = False
    message: str = ""
