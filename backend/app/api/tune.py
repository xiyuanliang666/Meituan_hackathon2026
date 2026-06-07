"""美甲款式微调 API。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.business_db import (
    find_style_id_by_image_url,
    get_user_demo_state,
    get_user_tune_history_item,
    save_user_tune_history,
    upsert_user_demo_state,
)
from app.services.image_tuning import get_tune_options, tune_nail_image

router = APIRouter()
DEMO_USER_ID = "demo_user"


# ─── 请求/响应 Schema ──────────────────────────────────────────


class TuneOverallRequest(BaseModel):
    style_image_url: str = Field(..., description="款式图 URL（平面图）")
    nail_shape_id: str | None = Field(default=None, description="甲型素材清单中的 ID")
    color: str | None = Field(default=None, description="目标颜色，十六进制或描述文字，如「#b5a89a」或「莫兰迪灰绿」")
    user_text: str | None = Field(default=None, description="用户自由文字描述")


class TuneSingleRequest(BaseModel):
    style_image_url: str = Field(..., description="款式图 URL（平面图）")
    finger_index: int = Field(..., ge=1, le=5, description="从左到右手指编号 1-5")
    action: str = Field(..., description="操作类型：color / french / decoration")
    color: str | None = Field(default=None, description="目标颜色（action=color 时使用）")
    french_style: str | None = Field(default=None, description="法式款式名（action=french 时使用）")
    decoration: str | None = Field(default=None, description="装饰品类型（action=decoration 时使用）")


class TuneResponse(BaseModel):
    tuned_image_url: str
    generation_mode: str = "mock"
    warnings: list[str] = []


@router.get("/tune/options")
def tune_options() -> dict:
    try:
        return get_tune_options()
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/tune/overall", response_model=TuneResponse)
def tune_overall(request: TuneOverallRequest) -> TuneResponse:
    """整体调整：换甲型 / 换颜色 / 自由文字描述"""
    if not request.style_image_url:
        raise HTTPException(status_code=400, detail="style_image_url is required")
    if not request.nail_shape_id and not request.color:
        raise HTTPException(status_code=400, detail="至少选择甲型或颜色")

    try:
        result = tune_nail_image(
            style_image_url=request.style_image_url,
            mode="overall",
            nail_shape_id=request.nail_shape_id,
            color=request.color,
            user_text=request.user_text,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result.get("tuned_image_url") and str(result.get("generation_mode") or "") != "local_svg_fallback":
        source_style_id = find_style_id_by_image_url(request.style_image_url)
        if not source_style_id:
            state = get_user_demo_state(DEMO_USER_ID) or {}
            tune_id = state.get("current_tune_id")
            prev_tune = get_user_tune_history_item(tune_id) if tune_id else None
            if prev_tune and request.style_image_url in {
                prev_tune.get("tuned_image_url"),
                prev_tune.get("source_style_image_url"),
            }:
                source_style_id = prev_tune.get("source_style_id")
        saved = save_user_tune_history(
            user_id=DEMO_USER_ID,
            source_style_id=source_style_id,
            source_style_image_url=request.style_image_url,
            tuned_image_url=result["tuned_image_url"],
            nail_shape_id=request.nail_shape_id,
            color=request.color,
            user_text=request.user_text,
            generation_mode=result.get("generation_mode", "mock"),
        )
        upsert_user_demo_state(DEMO_USER_ID, current_tune_id=saved["tune_id"])
    return TuneResponse(**result)


@router.post("/tune/single", response_model=TuneResponse)
def tune_single(request: TuneSingleRequest) -> TuneResponse:
    """单指微调：换色 / 法式 / 装饰品"""
    if not request.style_image_url:
        raise HTTPException(status_code=400, detail="style_image_url is required")
    valid_actions = {"color", "french", "decoration"}
    if request.action not in valid_actions:
        raise HTTPException(status_code=400, detail=f"action 必须为 {valid_actions} 之一")

    if request.action == "color" and not request.color:
        raise HTTPException(status_code=400, detail="action=color 时 color 字段不能为空")
    if request.action == "french" and not request.french_style:
        raise HTTPException(status_code=400, detail="action=french 时 french_style 字段不能为空")
    if request.action == "decoration" and not request.decoration:
        raise HTTPException(status_code=400, detail="action=decoration 时 decoration 字段不能为空")

    result = tune_nail_image(
        style_image_url=request.style_image_url,
        mode="single",
        finger_index=request.finger_index,
        action=request.action,
        color=request.color,
        french_style=request.french_style,
        decoration=request.decoration,
    )
    return TuneResponse(**result)
