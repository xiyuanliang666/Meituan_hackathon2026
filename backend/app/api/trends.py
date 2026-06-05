from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.schemas.trends import (
    CandidateTaxonomyTermItem,
    CandidateTaxonomyTermListResponse,
    CandidateTaxonomyTermUpdateRequest,
    DataHealthResponse,
    TrendDetailResponse,
    TrendActionRequest,
    TrendActionResponse,
    TrendConvertToDraftRequest,
    TrendConvertToDraftResponse,
    TrendPushToQueueRequest,
    TrendPushToQueueResponse,
    TrendListItem,
    TrendPipelineRunCreateRequest,
    TrendPipelineRunResponse,
    TrendRunCreateRequest,
    TrendRunResponse,
    UGCImportRequest,
    UGCImportResponse,
)
from app.services.business_db import (
    create_trend_pipeline_run,
    create_trend_run,
    get_data_health,
    get_trend,
    get_trend_pipeline_run,
    get_trend_run,
    import_ugc_posts,
    init_db,
    list_candidate_taxonomy_terms,
    list_trend_pipeline_runs,
    list_trends,
    set_pending_push_trends,
    update_candidate_taxonomy_term_status,
    update_trend_run,
)
from app.services.trend_jobs import execute_trend_run
from app.services.trend_materialization import convert_trend_to_draft
from app.services.trend_pipeline import execute_trend_pipeline


router = APIRouter()
ALLOWED_TREND_ACTIONS = {"viewed", "accepted", "ignored", "watching", "converted_to_draft"}
TREND_RUN_EXECUTOR = ThreadPoolExecutor(max_workers=2)
TREND_PIPELINE_EXECUTOR = ThreadPoolExecutor(max_workers=1)


class TrendListResponse(BaseModel):
    trends: list[TrendListItem]


class TrendPipelineRunListResponse(BaseModel):
    runs: list[TrendPipelineRunResponse]


@router.post("/trend-agent/ugc/import", response_model=UGCImportResponse)
def import_ugc_posts_endpoint(request: UGCImportRequest) -> UGCImportResponse:
    init_db(seed=True)
    return UGCImportResponse(**import_ugc_posts(request.posts))


@router.post("/trend-agent/runs", response_model=TrendRunResponse)
def create_trend_run_endpoint(request: TrendRunCreateRequest) -> TrendRunResponse:
    init_db(seed=True)
    run = create_trend_run(triggered_by=request.triggered_by, total_posts=0, status="pending")
    try:
        TREND_RUN_EXECUTOR.submit(execute_trend_run, run["run_id"], request.min_support, request.max_trends)
        created = get_trend_run(run["run_id"])
        if not created:
            raise HTTPException(status_code=500, detail="trend run create failed")
        return TrendRunResponse(**created)
    except Exception as exc:
        updated = update_trend_run(
            run["run_id"],
            status="failed",
            error_message=str(exc),
        )
        if updated:
            return TrendRunResponse(**updated)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/trend-agent/runs/{run_id}", response_model=TrendRunResponse)
def get_trend_run_endpoint(run_id: str) -> TrendRunResponse:
    init_db(seed=True)
    run = get_trend_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="trend run not found")
    return TrendRunResponse(**run)


@router.post("/trend-agent/pipeline-runs", response_model=TrendPipelineRunResponse)
def create_trend_pipeline_run_endpoint(request: TrendPipelineRunCreateRequest) -> TrendPipelineRunResponse:
    init_db(seed=True)
    if request.posts and request.seed_links:
        raise HTTPException(status_code=400, detail="posts and seed_links cannot be provided together")
    created = create_trend_pipeline_run(
        triggered_by=request.triggered_by,
        input_json_path=request.input_json_path,
        output_json_path=request.output_json_path,
        raw_comments_file=request.raw_comments_file,
        provider=request.provider,
        total_posts=0,
        auto_convert_to_draft=request.auto_convert_to_draft,
    )
    TREND_PIPELINE_EXECUTOR.submit(
        execute_trend_pipeline,
        pipeline_run_id=created["pipeline_run_id"],
        input_json_path=request.input_json_path,
        output_json_path=request.output_json_path,
        raw_comments_file=request.raw_comments_file,
        inline_posts=request.posts,
        seed_links=request.seed_links,
        user_data_dir=request.user_data_dir,
        provider=request.provider,
        limit=request.limit,
        refresh_ttl_hours=request.refresh_ttl_hours,
        only_missing=request.only_missing,
        force_refresh=request.force_refresh,
        skip_comment_pipeline=request.skip_comment_pipeline,
        comment_limit=request.comment_limit,
        login_wait_seconds=request.login_wait_seconds,
        min_support=request.min_support,
        max_trends=request.max_trends,
        resume=request.resume,
        from_start=request.from_start,
        force_summary=request.force_summary,
        headless=request.headless,
        auto_convert_to_draft=request.auto_convert_to_draft,
        convert_limit=request.convert_limit,
        merchant_id=request.merchant_id,
        use_trend_tags=request.use_trend_tags,
    )
    latest = get_trend_pipeline_run(created["pipeline_run_id"])
    if not latest:
        raise HTTPException(status_code=500, detail="trend pipeline run create failed")
    return TrendPipelineRunResponse(**latest)


@router.get("/trend-agent/pipeline-runs", response_model=TrendPipelineRunListResponse)
def list_trend_pipeline_runs_endpoint(limit: int = Query(default=20, ge=1, le=100)) -> TrendPipelineRunListResponse:
    init_db(seed=True)
    return TrendPipelineRunListResponse(runs=[TrendPipelineRunResponse(**item) for item in list_trend_pipeline_runs(limit=limit)])


@router.get("/trend-agent/pipeline-runs/{pipeline_run_id}", response_model=TrendPipelineRunResponse)
def get_trend_pipeline_run_endpoint(pipeline_run_id: str) -> TrendPipelineRunResponse:
    init_db(seed=True)
    run = get_trend_pipeline_run(pipeline_run_id)
    if not run:
        raise HTTPException(status_code=404, detail="trend pipeline run not found")
    return TrendPipelineRunResponse(**run)


@router.get("/trends", response_model=TrendListResponse)
def list_trends_endpoint(
    limit: int = Query(default=50, ge=1, le=200),
    status: str | None = Query(default=None),
    life_cycle: str | None = Query(default=None),
) -> TrendListResponse:
    init_db(seed=True)
    return TrendListResponse(trends=[TrendListItem(**item) for item in list_trends(limit=limit, status=status, life_cycle=life_cycle)])


@router.get("/trends/data-health", response_model=DataHealthResponse)
def get_data_health_endpoint() -> DataHealthResponse:
    """Return pipeline data health for pre-flight validation."""
    init_db(seed=True)
    return DataHealthResponse(**get_data_health())


@router.get("/trends/candidate-taxonomy", response_model=CandidateTaxonomyTermListResponse)
def list_candidate_taxonomy_endpoint(
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> CandidateTaxonomyTermListResponse:
    """List candidate taxonomy terms for ops review."""
    init_db(seed=True)
    terms = list_candidate_taxonomy_terms(status=status, limit=limit)
    return CandidateTaxonomyTermListResponse(
        terms=[CandidateTaxonomyTermItem(**item) for item in terms]
    )


@router.get("/trends/{trend_id}", response_model=TrendDetailResponse)
def get_trend_endpoint(trend_id: str) -> TrendDetailResponse:
    init_db(seed=True)
    trend = get_trend(trend_id)
    if not trend:
        raise HTTPException(status_code=404, detail="trend not found")
    return TrendDetailResponse(**trend)


@router.post("/trends/{trend_id}/actions", response_model=TrendActionResponse)
def create_trend_action_endpoint(trend_id: str, request: TrendActionRequest) -> TrendActionResponse:
    init_db(seed=True)
    trend = get_trend(trend_id)
    if not trend:
        raise HTTPException(status_code=404, detail="trend not found")
    action = request.action.strip()
    if action not in ALLOWED_TREND_ACTIONS:
        raise HTTPException(status_code=400, detail=f"unsupported action: {action}")
    from app.services.business_db import create_merchant_trend_action

    created = create_merchant_trend_action(merchant_id=request.merchant_id.strip(), trend_id=trend_id, action=action, note=request.note.strip())
    return TrendActionResponse(**created)


@router.put("/trends/candidate-taxonomy/{candidate_term}", response_model=CandidateTaxonomyTermItem)
def update_candidate_taxonomy_endpoint(
    candidate_term: str,
    request: CandidateTaxonomyTermUpdateRequest,
    target_field: str = Query(default="style_tags"),
) -> CandidateTaxonomyTermItem:
    """Approve or reject a candidate taxonomy term. When approved, the term is added to the live taxonomy."""
    init_db(seed=True)

    # Resolve edited values (fall back to originals)
    final_term = (request.candidate_term or candidate_term).strip()
    final_normalized = (request.normalized_form or request.candidate_term or candidate_term).strip()
    final_field = (request.target_field or target_field).strip()

    updated = update_candidate_taxonomy_term_status(
        candidate_term=candidate_term,
        target_field=target_field,
        status=request.status,
        new_candidate_term=final_term,
        new_normalized_form=final_normalized,
        new_target_field=final_field,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="candidate term not found")

    # When approved, add the term to the live taxonomy_options table
    if request.status == "approved":
        from uuid import uuid4
        from app.services.business_db import connect_db, _now
        with connect_db() as conn:
            import app.services.taxonomy_store as taxonomy_store
            taxonomy_store._ensure_tables(conn)
            taxonomy_store.ensure_taxonomy_seeded(conn)
            conn.execute(
                """
                INSERT OR REPLACE INTO taxonomy_options
                (option_id, field_key, value, is_approved, source, created_at)
                VALUES (?, ?, ?, 1, 'trend_candidate', ?)
                """,
                (f"opt-{uuid4().hex[:12]}", final_field, final_normalized, _now()),
            )

    return CandidateTaxonomyTermItem(**updated)


@router.post("/trends/{trend_id}/convert-to-draft", response_model=TrendConvertToDraftResponse)
def convert_trend_to_draft_endpoint(trend_id: str, request: TrendConvertToDraftRequest) -> TrendConvertToDraftResponse:
    init_db(seed=True)
    try:
        created = convert_trend_to_draft(
            trend_id=trend_id,
            merchant_id=request.merchant_id.strip(),
            style_name=request.style_name,
            use_trend_tags=request.use_trend_tags,
            note=request.note.strip(),
        )
    except Exception as exc:
        detail = str(exc)
        status_code = 404 if detail == "trend not found" else 400 if detail == "trend has no usable image" else 409
        raise HTTPException(status_code=status_code, detail=detail if status_code != 409 else f"draft creation failed: {detail}") from exc

    return TrendConvertToDraftResponse(
        trend_id=trend_id,
        style_id=created["style_id"],
        style_name=created["style_name"],
        image_url=created["image_url"],
        status=created["status"],
        review_status=created["review_status"],
        material_status=created.get("material_status", "ready"),
        source=created.get("source", "trend_agent"),
        source_trend_id=created.get("source_trend_id") or trend_id,
        tags=created.get("tags", {}),
    )


@router.post("/trends/{trend_id}/push-to-queue", response_model=TrendPushToQueueResponse)
def push_trend_to_queue_endpoint(trend_id: str, request: TrendPushToQueueRequest) -> TrendPushToQueueResponse:
    init_db(seed=True)
    trend = get_trend(trend_id)
    if not trend:
        raise HTTPException(status_code=404, detail="trend not found")
    try:
        result = set_pending_push_trends([trend_id], merchant_id=request.merchant_id.strip())
        pushed = len(result.get("requested_trend_ids", [])) > 0 and len(result.get("missing_trend_ids", [])) == 0
        from app.services.business_db import _push_id_for_trend
        push_id = _push_id_for_trend(trend_id) if pushed else ""
        return TrendPushToQueueResponse(
            trend_id=trend_id,
            push_id=push_id,
            pushed=pushed,
            message=f"趋势「{trend.get('core_style') or trend_id}」已加入爆款推送队列" if pushed else "加入推送队列失败",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

