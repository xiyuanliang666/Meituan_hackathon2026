from fastapi import APIRouter, HTTPException, Query

from app.schemas.hand_standardize import (
    StandardizeHandRequest,
    StandardizeHandResponse,
    SyncHandsRequest,
    UserHandsResponse,
)
from app.services.hand_standardizer import (
    get_user_hand_status,
    get_user_hands,
    standardize_hand,
    sync_user_hands,
)

router = APIRouter()


@router.post("/standardize-hand", response_model=StandardizeHandResponse)
def standardize_hand_image(request: StandardizeHandRequest) -> StandardizeHandResponse:
    if not request.hand_image_url.strip():
        raise HTTPException(status_code=400, detail="hand_image_url is required")
    return standardize_hand(request)


@router.get("/user-hand-status")
def user_hand_status(user_id: str = Query(..., min_length=1)) -> dict:
    return get_user_hand_status(user_id)


@router.get("/user-hands", response_model=UserHandsResponse)
def user_hands(user_id: str = Query(..., min_length=1)) -> UserHandsResponse:
    return get_user_hands(user_id)


@router.put("/user-hands/sync", response_model=UserHandsResponse)
def sync_hands(request: SyncHandsRequest) -> UserHandsResponse:
    return sync_user_hands(request)
