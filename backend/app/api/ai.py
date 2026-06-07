from fastapi import APIRouter, HTTPException

from app.schemas.hand import AnalyzeHandRequest, HandProfileResponse
from app.schemas.recommendation import RecommendationRequest, RecommendationResponse
from app.services.business_db import save_recommendation_snapshot, upsert_user_demo_state
from app.services.hand_analyzer import analyze_hand, get_hand_profile
from app.services.recommender import recommend_styles

router = APIRouter()


@router.post("/analyze-hand", response_model=HandProfileResponse)
def analyze_hand_profile(request: AnalyzeHandRequest) -> HandProfileResponse:
    if not request.hand_image_url:
        raise HTTPException(status_code=400, detail="hand_image_url is required")
    return analyze_hand(request)


@router.get("/hand-profile/{hand_profile_id}", response_model=HandProfileResponse)
def get_hand_profile_by_id(hand_profile_id: str) -> HandProfileResponse:
    profile = get_hand_profile(hand_profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="hand profile not found")
    return profile


@router.post("/recommendations", response_model=RecommendationResponse)
def recommendations(request: RecommendationRequest) -> RecommendationResponse:
    if request.limit < 1 or request.limit > 20:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 20")
    response = recommend_styles(request)
    if request.user_id and request.hand_profile_id:
        snapshot = save_recommendation_snapshot(
            user_id=request.user_id,
            hand_profile_id=request.hand_profile_id,
            query=request.query,
            recommendations=[item.model_dump() for item in response.recommendations],
        )
        upsert_user_demo_state(
            request.user_id,
            current_hand_profile_id=request.hand_profile_id,
            current_recommendation_snapshot_id=snapshot["snapshot_id"],
        )
    return response

