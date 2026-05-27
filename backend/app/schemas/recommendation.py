from pydantic import BaseModel, Field


class RecommendationRequest(BaseModel):
    user_id: str | None = None
    hand_profile_id: str | None = None
    query: str | None = None
    skin_tone: str | None = None
    hand_shape: str | None = None
    limit: int = Field(default=4, ge=1, le=20)


class RecommendationItem(BaseModel):
    style_id: str
    style_name: str
    image_url: str
    reason: str
    matched_tags: list[str]
    score: float


class RecommendationResponse(BaseModel):
    recommendations: list[RecommendationItem]

