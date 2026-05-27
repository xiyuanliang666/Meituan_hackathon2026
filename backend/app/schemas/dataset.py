from pydantic import BaseModel


class EvaluationPair(BaseModel):
    pair_id: str
    hand_image_url: str
    style_image_url: str


class EvaluationStyle(BaseModel):
    style_id: str
    original_style_image_url: str | None = None
    enhanced_style_image_url: str


class EvaluationDataset(BaseModel):
    hand_templates: list[str]
    styles: list[EvaluationStyle]
    pairs: list[EvaluationPair]
