from fastapi import APIRouter, HTTPException, Query

from app.schemas.db import CreateEventRequest, DbEventResponse, EventStatsItem
from app.services.business_db import create_event, list_event_stats, list_events

router = APIRouter()

ALLOWED_EVENT_TYPES = {"exposure", "try_on", "favorite", "like", "dislike", "order"}


@router.post("/events", response_model=DbEventResponse)
def create_user_event(request: CreateEventRequest) -> DbEventResponse:
    if request.event_type not in ALLOWED_EVENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"event_type must be one of {sorted(ALLOWED_EVENT_TYPES)}",
        )
    if not request.style_id and not request.hand_template_id:
        raise HTTPException(status_code=400, detail="style_id or hand_template_id is required")

    return DbEventResponse(
        **create_event(
            event_type=request.event_type,
            user_id=request.user_id,
            style_id=request.style_id,
            hand_template_id=request.hand_template_id,
            source=request.source,
        )
    )


@router.get("/events", response_model=list[DbEventResponse])
def user_events(limit: int = Query(default=50, ge=1, le=200)) -> list[DbEventResponse]:
    return [DbEventResponse(**item) for item in list_events(limit=limit)]


@router.get("/events/stats", response_model=list[EventStatsItem])
def event_stats(limit: int = Query(default=50, ge=1, le=200)) -> list[EventStatsItem]:
    return [EventStatsItem(**item) for item in list_event_stats(limit=limit)]
