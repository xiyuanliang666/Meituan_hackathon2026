"""
美甲款式微调 API
- POST /api/tune/overall  整体调整（换色 / 换甲型）
- POST /api/tune/single   单指微调（换色 / 法式 / 装饰品）
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.image_tuning import tune_nail_image

router = APIRouter()


# ─── 请求/响应 Schema ──────────────────────────────────────────


class TuneOverallRequest(BaseModel):
    style_image_url: str = Field(..., description="款式图 URL（平面图）")
    nail_shape: str | None = Field(default=None, description="目标甲型，如「圆甲」「长梯甲」")
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


# ─── 路由 ──────────────────────────────────────────────────────


@router.post("/tune/overall", response_model=TuneResponse)
def tune_overall(request: TuneOverallRequest) -> TuneResponse:
    """整体调整：换甲型 / 换颜色 / 自由文字描述"""
    if not request.style_image_url:
        raise HTTPException(status_code=400, detail="style_image_url is required")
    if not request.nail_shape and not request.color and not request.user_text:
        raise HTTPException(status_code=400, detail="至少提供 nail_shape / color / user_text 之一")

    result = tune_nail_image(
        style_image_url=request.style_image_url,
        mode="overall",
        nail_shape=request.nail_shape,
        color=request.color,
        user_text=request.user_text,
    )
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
