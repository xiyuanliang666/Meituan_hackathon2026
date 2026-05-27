from fastapi import APIRouter, Query

from app.schemas.db import DbEventResponse, DbStyleResponse, DbSummaryResponse, TagSeedStylesResponse
from app.services.business_db import get_db_summary, init_db, list_events, list_styles
from app.services.tag_extractor import tag_seed_styles

router = APIRouter()


@router.post("/db/init", response_model=DbSummaryResponse)
def initialize_database() -> DbSummaryResponse:
    return DbSummaryResponse(tables=init_db(seed=True))


@router.get("/db/summary", response_model=DbSummaryResponse)
def database_summary() -> DbSummaryResponse:
    init_db(seed=True)
    return DbSummaryResponse(tables=get_db_summary())


@router.get("/db/styles", response_model=list[DbStyleResponse])
def database_styles(limit: int = Query(default=50, ge=1, le=200)) -> list[DbStyleResponse]:
    init_db(seed=True)
    return [DbStyleResponse(**item) for item in list_styles(limit=limit)]


@router.get("/db/events", response_model=list[DbEventResponse])
def database_events(limit: int = Query(default=50, ge=1, le=200)) -> list[DbEventResponse]:
    init_db(seed=True)
    return [DbEventResponse(**item) for item in list_events(limit=limit)]


@router.post("/db/tag-seed-styles", response_model=TagSeedStylesResponse)
def tag_seed_styles_endpoint(limit: int = Query(default=25, ge=1, le=100)) -> TagSeedStylesResponse:
    return TagSeedStylesResponse(**tag_seed_styles(limit=limit))
