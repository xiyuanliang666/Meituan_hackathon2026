from __future__ import annotations

from pydantic import BaseModel, Field

# ── dimensions for each target type ──────────────────────────────
TRY_ON_DIMENSIONS = ["style_fidelity", "hand_fidelity", "size_compatibility"]
CHAT_DIMENSIONS = ["retrieval_accuracy", "structure_completeness", "reason_accuracy"]
HAND_ANALYSIS_DIMENSIONS = [
    "skin_tone_accuracy",
    "hand_shape_accuracy",
    "recommendation_reasonableness",
    "reason_quality",
]

TARGET_DIMENSIONS: dict[str, list[str]] = {
    "try_on": TRY_ON_DIMENSIONS,
    "chat": CHAT_DIMENSIONS,
    "hand_analysis": HAND_ANALYSIS_DIMENSIONS,
}


class EvalSubmitRequest(BaseModel):
    target_type: str = Field(..., description="try_on | chat | hand_analysis")
    target_id: str = Field(..., description="style_id / conversation_id / hand_profile_id")
    scores: dict[str, int] = Field(..., description="dimension -> 1-5 score")
    comment: str = ""


class EvalRecord(BaseModel):
    target_type: str
    target_id: str
    scores: dict[str, int]
    comment: str


class DimStat(BaseModel):
    avg: float
    count: int


class EvalStatsResponse(BaseModel):
    target_type: str
    total_submissions: int
    dimensions: dict[str, DimStat]
