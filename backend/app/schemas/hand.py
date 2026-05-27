from pydantic import BaseModel


class AnalyzeHandRequest(BaseModel):
    user_id: str | None = None
    hand_image_url: str


class HandProfileResponse(BaseModel):
    hand_profile_id: str
    user_id: str | None = None
    skin_tone: str
    hand_shape: str
    recommended_colors: list[str]
    recommended_styles: list[str]
    recommended_nail_shapes: list[str]
    analysis_reason: str
    analysis_mode: str = "mock"
