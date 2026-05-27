from pydantic import BaseModel, Field


class DbSummaryResponse(BaseModel):
    tables: dict[str, int]


class TagSeedStylesResponse(BaseModel):
    total_styles: int
    updated_styles: int
    failed_styles: int
    analysis_modes: dict[str, int]


class DbStyleResponse(BaseModel):
    style_id: str
    original_style_image_url: str | None
    enhanced_style_image_url: str
    style_name: str | None
    tags: dict[str, list[str]]
    hot_score: float
    life_cycle: str


class DbEventResponse(BaseModel):
    event_id: str
    user_id: str | None = None
    style_id: str | None = None
    hand_template_id: str | None = None
    event_type: str
    source: str
    created_at: str


class CreateEventRequest(BaseModel):
    user_id: str | None = None
    style_id: str | None = None
    hand_template_id: str | None = None
    event_type: str = Field(..., examples=["exposure", "try_on", "favorite", "like", "dislike", "order"])
    source: str = Field(default="demo", examples=["user_h5", "merchant_web", "demo"])


class EventStatsItem(BaseModel):
    style_id: str
    style_name: str | None = None
    exposure_count: int = 0
    try_on_count: int = 0
    favorite_count: int = 0
    like_count: int = 0
    dislike_count: int = 0
    order_count: int = 0
    try_rate: float = 0
    favorite_rate: float = 0
    order_rate: float = 0

