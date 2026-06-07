"""美甲款式微调 API。"""

from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.business_db import (
    find_style_id_by_image_url,
    get_user_demo_state,
    get_user_hand_asset,
    get_user_tune_history_item,
    save_user_tune_history,
    upsert_user_demo_state,
)
from app.services.hand_nail_regions import get_hand_nail_region_payload
from app.services.tryon_history import get_tryon_record
from app.services.image_tuning import get_tune_options, tune_nail_image

router = APIRouter()
DEMO_USER_ID = "demo_user"


# ─── 请求/响应 Schema ──────────────────────────────────────────


class TuneOverallRequest(BaseModel):
    style_image_url: str = Field(..., description="款式图 URL（平面图）")
    nail_shape_id: str | None = Field(default=None, description="甲型素材清单中的 ID")
    color: str | None = Field(default=None, description="目标颜色，十六进制或描述文字，如「#b5a89a」或「莫兰迪灰绿」")
    user_text: str | None = Field(default=None, description="用户自由文字描述")
    hand_id: str | None = Field(default=None, description="当前试戴所对应的用户手图 ID")
    tryon_record_id: str | None = Field(default=None, description="当前试戴记录 ID")


class TuneSingleRequest(BaseModel):
    style_image_url: str = Field(..., description="款式图 URL（平面图）")
    finger_index: int = Field(..., ge=1, le=5, description="从左到右手指编号 1-5")
    action: str = Field(..., description="操作类型：color / french / decoration")
    color: str | None = Field(default=None, description="目标颜色（action=color 时使用）")
    french_style: str | None = Field(default=None, description="法式款式名（action=french 时使用）")
    decoration: str | None = Field(default=None, description="装饰品类型（action=decoration 时使用）")
    hand_id: str | None = Field(default=None, description="当前试戴所对应的用户手图 ID")
    tryon_record_id: str | None = Field(default=None, description="当前试戴记录 ID")
    guide_image_url: str | None = Field(default=None, description="前端生成的单指高亮标注图，可为 data URL")


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
    _ensure_tune_hand_ready(
        style_image_url=request.style_image_url,
        hand_id=request.hand_id,
        tryon_record_id=request.tryon_record_id,
    )

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
    _persist_tune_result(
        style_image_url=request.style_image_url,
        tuned_image_url=result.get("tuned_image_url", ""),
        generation_mode=str(result.get("generation_mode") or "mock"),
        nail_shape_id=request.nail_shape_id,
        color=request.color,
        user_text=request.user_text,
    )
    return TuneResponse(**result)


def _ensure_tune_hand_ready(*, style_image_url: str, hand_id: str | None, tryon_record_id: str | None) -> None:
    resolved_hand_id = hand_id
    if tryon_record_id:
        record = get_tryon_record(tryon_record_id)
        if record is None:
            raise HTTPException(status_code=400, detail="未找到对应的试戴记录，请重新试戴后再进行 AI 微调")
        if record.get("user_id") != DEMO_USER_ID:
            raise HTTPException(status_code=403, detail="当前试戴记录不可用于 AI 微调")
        if not _matches_tune_source(str(record.get("result_image_url") or ""), style_image_url):
            raise HTTPException(status_code=400, detail="当前微调图片与试戴记录不匹配，请重新打开微调页面")
        resolved_hand_id = str(record.get("hand_id") or resolved_hand_id or "").strip()

    resolved_hand_id = str(resolved_hand_id or "").strip()
    if not resolved_hand_id:
        raise HTTPException(status_code=400, detail="请先完成手图试戴，确认手图解析成功后再使用 AI 微调")

    hand_asset = get_user_hand_asset(resolved_hand_id, DEMO_USER_ID)
    if hand_asset is None:
        raise HTTPException(status_code=400, detail="未找到当前手图记录，请重新上传手图后再试")

    status = str(hand_asset.get("nail_region_status") or "pending")
    error = str(hand_asset.get("nail_region_error") or "").strip()
    json_path = str(hand_asset.get("nail_region_json_path") or "").strip()
    if status != "done" or not json_path or not Path(json_path).exists():
        detail = error or "当前手图甲面解析失败，请重新上传更清晰的手图后再使用 AI 微调"
        raise HTTPException(status_code=400, detail=detail)


def _same_image_reference(left: str, right: str) -> bool:
    if left == right:
        return True
    left_path = urlparse(left).path or left
    right_path = urlparse(right).path or right
    return left_path == right_path or left_path.endswith(right_path) or right_path.endswith(left_path)


def _matches_tune_source(tryon_result_image_url: str, style_image_url: str) -> bool:
    if _same_image_reference(tryon_result_image_url, style_image_url):
        return True
    state = get_user_demo_state(DEMO_USER_ID) or {}
    tune_id = str(state.get("current_tune_id") or "").strip()
    prev_tune = get_user_tune_history_item(tune_id) if tune_id else None
    if not prev_tune:
        return False
    return any(
        _same_image_reference(str(candidate or ""), style_image_url)
        for candidate in (
            prev_tune.get("tuned_image_url"),
            prev_tune.get("source_style_image_url"),
        )
    )


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
    _ensure_tune_hand_ready(
        style_image_url=request.style_image_url,
        hand_id=request.hand_id,
        tryon_record_id=request.tryon_record_id,
    )

    result = tune_nail_image(
        style_image_url=request.style_image_url,
        mode="single",
        finger_index=request.finger_index,
        action=request.action,
        color=request.color,
        french_style=request.french_style,
        decoration=request.decoration,
        guide_image_url=request.guide_image_url,
        finger_region=_get_finger_region(request.hand_id, request.tryon_record_id, request.finger_index),
    )
    _persist_tune_result(
        style_image_url=request.style_image_url,
        tuned_image_url=result.get("tuned_image_url", ""),
        generation_mode=str(result.get("generation_mode") or "mock"),
        color=request.color,
        user_text=_single_action_summary(request),
    )
    return TuneResponse(**result)


def _get_finger_region(hand_id: str | None, tryon_record_id: str | None, finger_index: int) -> list[list[float]] | None:
    resolved_hand_id = str(hand_id or "").strip()
    if tryon_record_id:
        record = get_tryon_record(tryon_record_id)
        if record:
            resolved_hand_id = str(record.get("hand_id") or resolved_hand_id or "").strip()
    if not resolved_hand_id:
        return None
    payload = get_hand_nail_region_payload(resolved_hand_id)
    if not payload:
        return None
    region = payload.get("nail_regions", {}).get(str(finger_index))
    return region if isinstance(region, list) else None


def _persist_tune_result(
    *,
    style_image_url: str,
    tuned_image_url: str,
    generation_mode: str,
    nail_shape_id: str | None = None,
    color: str | None = None,
    user_text: str | None = None,
) -> None:
    if not tuned_image_url or generation_mode == "local_svg_fallback":
        return
    source_style_id = find_style_id_by_image_url(style_image_url)
    if not source_style_id:
        state = get_user_demo_state(DEMO_USER_ID) or {}
        tune_id = state.get("current_tune_id")
        prev_tune = get_user_tune_history_item(tune_id) if tune_id else None
        if prev_tune and any(
            _same_image_reference(style_image_url, str(candidate or ""))
            for candidate in (
                prev_tune.get("tuned_image_url"),
                prev_tune.get("source_style_image_url"),
            )
        ):
            source_style_id = prev_tune.get("source_style_id")
    saved = save_user_tune_history(
        user_id=DEMO_USER_ID,
        source_style_id=source_style_id,
        source_style_image_url=style_image_url,
        tuned_image_url=tuned_image_url,
        nail_shape_id=nail_shape_id,
        color=color,
        user_text=user_text,
        generation_mode=generation_mode,
    )
    if saved.get("tune_id"):
        upsert_user_demo_state(DEMO_USER_ID, current_tune_id=saved["tune_id"])


def _single_action_summary(request: TuneSingleRequest) -> str:
    if request.action == "color":
        return f"single-finger color={request.color or ''} finger={request.finger_index}"
    if request.action == "french":
        return f"single-finger french={request.french_style or ''} finger={request.finger_index}"
    if request.action == "decoration":
        return f"single-finger decoration={request.decoration or ''} finger={request.finger_index}"
    return f"single-finger action={request.action} finger={request.finger_index}"
