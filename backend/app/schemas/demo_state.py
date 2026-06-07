from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.tryon_history import TryOnHistoryItem


class DemoCurrentHand(BaseModel):
    user_id: str
    hand_id: str
    image_url: str
    selected: bool = True
    quality_pass: bool = True
    quality_issues: list[str] = Field(default_factory=list)
    nail_art_detected: bool = False
    processing_note: str = ""
    created_at: str = ""
    updated_at: str = ""


class DemoHandProfile(BaseModel):
    hand_profile_id: str
    user_id: str | None = None
    hand_id: str | None = None
    hand_image_url: str
    skin_tone: str
    hand_shape: str
    recommended_colors: list[str] = Field(default_factory=list)
    recommended_styles: list[str] = Field(default_factory=list)
    recommended_nail_shapes: list[str] = Field(default_factory=list)
    analysis_reason: str = ""
    analysis_mode: str = "mock"
    created_at: str = ""


class RecommendationSnapshotItem(BaseModel):
    style_id: str
    style_name: str
    image_url: str = ""
    reason: str = ""
    matched_tags: list[str] = Field(default_factory=list)
    score: float = 0


class DemoRecommendationSnapshot(BaseModel):
    snapshot_id: str
    user_id: str
    hand_profile_id: str
    query: str = ""
    recommendations: list[RecommendationSnapshotItem] = Field(default_factory=list)
    created_at: str = ""


class DemoCurrentTune(BaseModel):
    tune_id: str
    user_id: str
    source_style_id: str | None = None
    source_style_image_url: str
    tuned_image_url: str
    nail_shape_id: str | None = None
    color: str | None = None
    user_text: str | None = None
    generation_mode: str = "mock"
    created_at: str = ""


class DemoStateResponse(BaseModel):
    user_id: str
    current_hand: DemoCurrentHand | None = None
    hand_profile: DemoHandProfile | None = None
    recommendation_snapshot: DemoRecommendationSnapshot | None = None
    current_tune: DemoCurrentTune | None = None
    tryon_records: list[TryOnHistoryItem] = Field(default_factory=list)

