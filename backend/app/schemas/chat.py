from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, examples=["肉手短甲适合什么甲型？"])
    user_id: str | None = None
    hand_profile_id: str | None = None
    conversation_id: str | None = None


class ChatRecommendationItem(BaseModel):
    style_id: str
    style_name: str
    image_url: str
    reason: str


class ChatAnswer(BaseModel):
    scene_analysis: str = ""
    recommendations: list[ChatRecommendationItem] = Field(default_factory=list)
    tips: str = ""
    follow_up: str = ""


class ChatResponse(BaseModel):
    conversation_id: str
    answer: ChatAnswer
    suggested_questions: list[str] = Field(default_factory=list)
    generation_mode: str = "mock"
