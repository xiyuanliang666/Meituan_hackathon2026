from pydantic import BaseModel, Field


class ExtractTagsRequest(BaseModel):
    image_url: str = Field(..., examples=["https://example.com/nail.png"])
    style_id: str | None = Field(default=None, examples=["style-seed-001"])


class UploadImageResponse(BaseModel):
    image_url: str
    filename: str
    content_type: str
    size_bytes: int


class StyleTagsResponse(BaseModel):
    style_id: str | None = None
    color_system: list[str] = Field(default_factory=list)
    style_tags: list[str] = Field(default_factory=list)
    scene_tags: list[str] = Field(default_factory=list)
    season_tags: list[str] = Field(default_factory=list)
    skin_tone_suitability: list[str] = Field(default_factory=list)
    nail_technique: list[str] = Field(default_factory=list)
    nail_decoration: list[str] = Field(default_factory=list)
    nail_finish: str = "unknown"
    nail_shape: str = "unknown"
    nail_length: str = "unknown"
    finger_shape: str = "unknown"
    nail_bed_shape: str = "unknown"
    candidate_tags: list[str] = Field(default_factory=list)
    analysis_mode: str = "mock"


class UpdateStyleTagsRequest(BaseModel):
    color_system: list[str] = Field(default_factory=list)
    style_tags: list[str] = Field(default_factory=list)
    scene_tags: list[str] = Field(default_factory=list)
    season_tags: list[str] = Field(default_factory=list)
    skin_tone_suitability: list[str] = Field(default_factory=list)
    nail_technique: list[str] = Field(default_factory=list)
    nail_decoration: list[str] = Field(default_factory=list)
    nail_finish: str = "unknown"
    nail_shape: str = "unknown"
    nail_length: str = "unknown"
    finger_shape: str = "unknown"
    nail_bed_shape: str = "unknown"
    candidate_tags: list[str] = Field(default_factory=list)


class CompositeRequest(BaseModel):
    style_image_url: str
    template_image_url: str


class CompositeResponse(BaseModel):
    composite_image_url: str
    generation_mode: str = "mock"


class TryOnRequest(BaseModel):
    user_id: str | None = None
    hand_image_url: str
    style_image_url: str
    style_id: str | None = None


class TryOnResponse(BaseModel):
    result_image_url: str
    generation_mode: str = "mock"
    warnings: list[str] = []
