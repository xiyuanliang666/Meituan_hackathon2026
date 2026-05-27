from __future__ import annotations

from pydantic import BaseModel, Field


class StandardizeHandRequest(BaseModel):
    hand_image_url: str = Field(..., description="用户上传的手部图片URL")
    user_id: str | None = None


class QualityDetails(BaseModel):
    fingers_up: bool = False
    full_hand_visible: bool = False
    fingers_spread: bool = False
    bright_lighting: bool = False
    clean_background: bool = False


class StandardizeHandResponse(BaseModel):
    standardized_hand_id: str
    standardized_image_url: str
    quality_pass: bool
    quality_details: QualityDetails
    quality_issues: list[str] = Field(default_factory=list)
    nail_art_detected: bool = False
    processing_note: str = ""


# ── multi-hand management ──

class UserHandItem(BaseModel):
    hand_id: str
    image_url: str
    selected: bool = False


class UserHandsResponse(BaseModel):
    user_id: str
    hands: list[UserHandItem]


class SyncHandsRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    hands: list[UserHandItem]
