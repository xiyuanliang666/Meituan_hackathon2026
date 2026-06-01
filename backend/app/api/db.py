from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.schemas.db import DbEventResponse, DbStyleResponse, DbSummaryResponse, ReportSnapshotItem, TagSeedStylesResponse
from app.services.business_db import get_db_summary, init_db, list_events, list_report_snapshots, list_styles
from app.services.tag_extractor import tag_seed_styles

router = APIRouter()


class StylesListResponse(BaseModel):
    styles: list[DbStyleResponse]


@router.post("/db/init", response_model=DbSummaryResponse)
def initialize_database() -> DbSummaryResponse:
    return DbSummaryResponse(tables=init_db(seed=True))


@router.get("/db/summary", response_model=DbSummaryResponse)
def database_summary() -> DbSummaryResponse:
    init_db(seed=True)
    return DbSummaryResponse(tables=get_db_summary())


@router.get("/db/styles", response_model=StylesListResponse)
def database_styles(
    limit: int = Query(default=50, ge=1, le=200),
    status: str | None = Query(default=None),
    q: str | None = Query(default=None),
) -> StylesListResponse:
    init_db(seed=True)
    return StylesListResponse(styles=[DbStyleResponse(**item) for item in list_styles(limit=limit, status=status, q=q)])


@router.get("/db/events", response_model=list[DbEventResponse])
def database_events(limit: int = Query(default=50, ge=1, le=200)) -> list[DbEventResponse]:
    init_db(seed=True)
    return [DbEventResponse(**item) for item in list_events(limit=limit)]


@router.get("/db/report-snapshots", response_model=list[ReportSnapshotItem])
def database_report_snapshots(limit: int = Query(default=20, ge=1, le=100)) -> list[ReportSnapshotItem]:
    init_db(seed=True)
    return [ReportSnapshotItem(**item) for item in list_report_snapshots(limit=limit)]


@router.post("/db/tag-seed-styles", response_model=TagSeedStylesResponse)
def tag_seed_styles_endpoint(limit: int = Query(default=25, ge=1, le=100)) -> TagSeedStylesResponse:
    return TagSeedStylesResponse(**tag_seed_styles(limit=limit))
