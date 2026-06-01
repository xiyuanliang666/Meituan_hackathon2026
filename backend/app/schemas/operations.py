from typing import Any, Literal

from pydantic import BaseModel


class SignalSource(BaseModel):
    signal: str
    value: float
    delta: float
    weight: float


class PushCardResponse(BaseModel):
    push_id: str
    style_id: str
    style_name: str
    style_tags: list[str]
    style_image_urls: list[str]
    signal_sources: list[SignalSource]
    hot_score: float
    life_cycle: str
    life_cycle_trend: list[float]
    coupon_url: str
    coupon_price: float
    tagline: str
    status: str = "pending"
    audit_details: dict[str, Any] = {}


class AuditPushCardRequest(BaseModel):
    merchant_id: str
    action: Literal["accepted", "rejected"]
    selected_image_url: str | None = None
    selected_coupon_url: str | None = None
    final_tagline: str | None = None
    final_price: float | None = None


class AuditPushCardResponse(BaseModel):
    success: bool
    push_id: str
    style_id: str
    status: str
    message: str
    selected_image_url: str | None = None
    selected_coupon_url: str | None = None
    final_tagline: str | None = None
    final_price: float | None = None


class ReportRequest(BaseModel):
    merchant_id: str | None = None
    period: str = "this_week"
    merchant_prefs: dict[str, Any] = {}
    current_period: dict[str, Any] = {}
    last_period: dict[str, Any] = {}
    hot_styles: list[dict[str, Any]] = []


class Suggestion(BaseModel):
    text: str
    action_type: str
    action_params: dict[str, Any]
    requires_confirm: bool
    adopted: bool = False


class ReportMetric(BaseModel):
    key: str
    label: str
    value: str
    delta: str = ""
    delta_direction: Literal["up", "down", "flat"] = "flat"


class ReportHotStyleItem(BaseModel):
    style_id: str
    style_name: str
    hot_score: float
    life_cycle: str
    try_on_count: int = 0
    favorite_count: int = 0
    order_count: int = 0
    favorite_rate: float = 0


class ReportResponse(BaseModel):
    report_summary: str
    suggestions: list[Suggestion]
    generation_mode: str = "mock"
    snapshot_id: str | None = None
    period_label: str = ""
    metrics: list[ReportMetric] = []
    hot_styles: list[ReportHotStyleItem] = []
    merchant_prefs: dict[str, Any] = {}


class SkillExecuteRequest(BaseModel):
    action_type: str
    action_params: dict[str, Any] = {}


class SkillExecuteResponse(BaseModel):
    success: bool
    action_type: str
    message: str
    state_patch: dict[str, Any] = {}
