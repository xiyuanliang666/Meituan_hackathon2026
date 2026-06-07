from __future__ import annotations

from fastapi import APIRouter, Query

from app.schemas.demo_state import DemoStateResponse
from app.schemas.tryon_history import TryOnHistoryItem
from app.services.demo_state import clear_demo_state_bundle, get_demo_state_bundle

router = APIRouter()


@router.get("/demo-state", response_model=DemoStateResponse)
def get_demo_state(user_id: str = Query(..., min_length=1)) -> DemoStateResponse:
    data = get_demo_state_bundle(user_id)
    return DemoStateResponse(
        user_id=data["user_id"],
        current_hand=data["current_hand"],
        hand_profile=data["hand_profile"],
        recommendation_snapshot=data["recommendation_snapshot"],
        current_tune=data["current_tune"],
        tryon_records=[TryOnHistoryItem(**item) for item in data["tryon_records"]],
    )


@router.delete("/demo-state")
def delete_demo_state(user_id: str = Query(..., min_length=1)) -> dict:
    clear_demo_state_bundle(user_id)
    return {"cleared": True, "user_id": user_id}
