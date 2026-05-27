from __future__ import annotations

from pydantic import BaseModel, Field


class TryOnHistoryItem(BaseModel):
    record_id: str
    user_id: str
    hand_id: str | None = None
    style_id: str | None = None
    hand_image_url: str
    style_image_url: str
    result_image_url: str
    created_at: str


class TryOnHistoryListResponse(BaseModel):
    records: list[TryOnHistoryItem]
    total: int


class BatchDeleteRequest(BaseModel):
    record_ids: list[str] = Field(..., min_length=1)


class RegenerateRequest(BaseModel):
    hand_image_url: str | None = None
    style_image_url: str | None = None
