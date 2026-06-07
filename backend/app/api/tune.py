"""美甲款式微调 API。"""

from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.business_db import (
    find_demo_tune_record_by_output,
    find_style_id_by_image_url,
    get_user_demo_state,
    get_user_hand_asset,
    get_user_tune_history_item,
    save_demo_tune_record,
    save_user_tune_history,
    upsert_user_demo_state,
    update_user_hand_nail_region_status,
)
from app.services.hand_standardizer import extract_and_store_hand_nail_regions
from app.services.hand_nail_regions import (
    get_hand_nail_region_payload,
    get_hand_nail_region_status,
    resolve_hand_nail_region_json_path,
)
from app.services.tryon_history import get_tryon_record
from app.services.image_tuning import get_tune_options, tune_nail_image

router = APIRouter()
DEMO_USER_ID = "demo_user"


# ─── 请求/响应 Schema ──────────────────────────────────────────


class TuneOverallRequest(BaseModel):
    style_image_url: str = Field(..., description="款式图 URL（平面图）")
    nail_shape_id: str | None = Field(default=None, description="甲型素材清单中的 ID")
    french_style_id: str | None = Field(default=None, description="法式素材清单中的 ID")
    color: str | None = Field(default=None, description="目标颜色，十六进制或描述文字，如「#b5a89a」或「莫兰迪灰绿」")
    user_text: str | None = Field(default=None, description="用户自由文字描述")
    hand_id: str | None = Field(default=None, description="当前试戴所对应的用户手图 ID")
    tryon_record_id: str | None = Field(default=None, description="当前试戴记录 ID")


class TuneSingleRequest(BaseModel):
    style_image_url: str = Field(..., description="款式图 URL（平面图）")
    finger_index: int = Field(..., ge=1, le=5, description="从左到右手指编号 1-5")
    action: str = Field(..., description="操作类型：color / french / decoration")
    color: str | None = Field(default=None, description="目标颜色（action=color 时使用）")
    french_style_id: str | None = Field(default=None, description="法式素材清单中的 ID（action=french 时使用）")
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
    if not request.nail_shape_id and not request.french_style_id and not request.color and not (request.user_text or "").strip():
        raise HTTPException(status_code=400, detail="至少选择甲型、法式风格、颜色或输入文字需求")
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
            french_style_id=request.french_style_id,
            color=request.color,
            user_text=request.user_text,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    saved = _persist_tune_result(
        style_image_url=request.style_image_url,
        tuned_image_url=result.get("tuned_image_url", ""),
        generation_mode=str(result.get("generation_mode") or "mock"),
        nail_shape_id=request.nail_shape_id,
        color=request.color,
        user_text=_overall_action_summary(request),
    )
    _persist_demo_tune_record_overall(request=request, tuned_image_url=result.get("tuned_image_url", ""), generation_mode=str(result.get("generation_mode") or "mock"), saved_tune=saved)
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

    asset_status = str(hand_asset.get("nail_region_status") or "pending")
    asset_error = str(hand_asset.get("nail_region_error") or "").strip()
    region_status = get_hand_nail_region_status(resolved_hand_id)
    status = str(region_status.get("status") or asset_status or "pending")
    error = str(region_status.get("error") or asset_error or "").strip()
    resolved_json_path = resolve_hand_nail_region_json_path(
        resolved_hand_id,
        str(hand_asset.get("nail_region_json_path") or region_status.get("json_path") or ""),
    )
    if status != "done" or resolved_json_path is None or not resolved_json_path.exists():
        refreshed = _try_refresh_hand_nail_regions(resolved_hand_id, hand_asset)
        if refreshed:
            status = str(refreshed.get("status") or status or "pending")
            error = str(refreshed.get("error") or error or "").strip()
            resolved_json_path = resolve_hand_nail_region_json_path(
                resolved_hand_id,
                str(refreshed.get("json_path") or hand_asset.get("nail_region_json_path") or ""),
            )
    if status != "done" or resolved_json_path is None or not resolved_json_path.exists():
        detail = error or "当前手图甲面解析失败，请重新上传更清晰的手图后再使用 AI 微调"
        raise HTTPException(status_code=400, detail=detail)


def _try_refresh_hand_nail_regions(hand_id: str, hand_asset: dict) -> dict | None:
    image_url = str(hand_asset.get("image_url") or "").strip()
    if not image_url:
        return None
    try:
        refreshed = extract_and_store_hand_nail_regions(
            hand_id=hand_id,
            image_url=image_url,
            hand_label=hand_id,
        )
    except Exception as exc:
        return {
            "status": "failed",
            "json_path": "",
            "error": str(exc),
        }

    update_user_hand_nail_region_status(
        DEMO_USER_ID,
        hand_id,
        status=str(refreshed.get("status") or "pending"),
        json_path=str(refreshed.get("json_path") or ""),
        error=str(refreshed.get("error") or ""),
    )
    return refreshed


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
    if request.action == "french" and not request.french_style_id:
        raise HTTPException(status_code=400, detail="action=french 时 french_style_id 字段不能为空")
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
        french_style_id=request.french_style_id,
        decoration=request.decoration,
        guide_image_url=request.guide_image_url,
        finger_region=_get_finger_region(request.hand_id, request.tryon_record_id, request.finger_index),
    )
    saved = _persist_tune_result(
        style_image_url=request.style_image_url,
        tuned_image_url=result.get("tuned_image_url", ""),
        generation_mode=str(result.get("generation_mode") or "mock"),
        color=request.color,
        user_text=_single_action_summary(request),
    )
    _persist_demo_tune_record_single(request=request, tuned_image_url=result.get("tuned_image_url", ""), generation_mode=str(result.get("generation_mode") or "mock"), saved_tune=saved)
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
) -> dict:
    if not tuned_image_url or generation_mode == "local_svg_fallback":
        return {}
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
    return saved


def _single_action_summary(request: TuneSingleRequest) -> str:
    if request.action == "color":
        return f"single-finger color={request.color or ''} finger={request.finger_index}"
    if request.action == "french":
        return f"single-finger french={request.french_style_id or ''} finger={request.finger_index}"
    if request.action == "decoration":
        return f"single-finger decoration={request.decoration or ''} finger={request.finger_index}"
    return f"single-finger action={request.action} finger={request.finger_index}"


def _overall_action_summary(request: TuneOverallRequest) -> str:
    return (
        f"overall shape={request.nail_shape_id or ''} "
        f"french={request.french_style_id or ''} "
        f"color={request.color or ''} "
        f"text={request.user_text or ''}"
    ).strip()


def _shape_label(shape_id: str | None) -> str:
    return {
        "doudou": "豆豆甲",
        "short_trapezoid": "短梯形",
        "medium_trapezoid": "中梯形",
        "long_trapezoid": "长梯形",
        "short_oval": "短椭圆",
        "medium_oval": "中椭圆",
        "long_oval": "长椭圆",
        "medium_square": "中方形",
    }.get(str(shape_id or ""), "")


def _french_label(french_style_id: str | None) -> str:
    return {
        "cross_french": "交叉法式",
        "standard_french": "标准法式",
        "diagonal_french": "斜法式",
        "outline_french": "轮廓法式",
    }.get(str(french_style_id or ""), "")


def _persist_demo_tune_record_overall(*, request: TuneOverallRequest, tuned_image_url: str, generation_mode: str, saved_tune: dict) -> None:
    if not request.tryon_record_id or not tuned_image_url or generation_mode == "local_svg_fallback":
        return
    root = get_tryon_record(request.tryon_record_id)
    if not root:
        return
    parent = find_demo_tune_record_by_output(request.style_image_url)
    shape_label = _shape_label(request.nail_shape_id)
    french_label = _french_label(request.french_style_id)
    raw_user_text = str(request.user_text or "").strip()
    operation_mode = "text_only" if not request.nail_shape_id and not request.french_style_id and not request.color and raw_user_text else "overall"
    operation_payload = {
        "nail_shape_id": request.nail_shape_id,
        "nail_shape_label": shape_label,
        "french_style_id": request.french_style_id,
        "french_style_label": french_label,
        "color": request.color,
        "user_text": raw_user_text or None,
    }
    if operation_mode == "text_only":
        operation_payload = {"user_text": raw_user_text}
        operation_summary = f"文字微调 · {_extract_visible_tune_text(raw_user_text)}"
    else:
        summary_parts = ["整体"]
        if shape_label:
            summary_parts.append(f"甲型={shape_label}")
        if french_label:
            summary_parts.append(f"法式={french_label}")
        if request.color:
            summary_parts.append(f"颜色={request.color}")
        operation_summary = " · ".join(summary_parts)
    save_demo_tune_record(
        tune_record_id=str(saved_tune.get("tune_id") or ""),
        root_tryon_record_id=str(root.get("record_id") or request.tryon_record_id),
        parent_tune_record_id=parent.get("tune_record_id") if parent else None,
        root_hand_id=str(root.get("hand_id") or request.hand_id or ""),
        root_style_id=str(root.get("style_id") or ""),
        root_tryon_image_url=str(root.get("result_image_url") or ""),
        input_image_url=request.style_image_url,
        output_image_url=tuned_image_url,
        operation_mode=operation_mode,
        operation_payload=operation_payload,
        operation_summary=operation_summary,
        generation_mode=generation_mode,
        created_at=str(saved_tune.get("created_at") or ""),
    )


def _persist_demo_tune_record_single(*, request: TuneSingleRequest, tuned_image_url: str, generation_mode: str, saved_tune: dict) -> None:
    if not request.tryon_record_id or not tuned_image_url or generation_mode == "local_svg_fallback":
        return
    root = get_tryon_record(request.tryon_record_id)
    if not root:
        return
    parent = find_demo_tune_record_by_output(request.style_image_url)
    french_label = _french_label(request.french_style_id)
    operation_payload = {
        "finger_index": request.finger_index,
        "action": request.action,
        "color": request.color,
        "french_style_id": request.french_style_id,
        "french_style_label": french_label,
        "decoration": request.decoration,
        "user_text": None,
    }
    if request.action == "color":
        operation_summary = f"单指 · 第{request.finger_index}指 · 颜色={request.color or ''}"
    elif request.action == "french":
        operation_summary = f"单指 · 第{request.finger_index}指 · 法式={french_label or request.french_style_id or ''}"
    else:
        operation_summary = f"单指 · 第{request.finger_index}指 · 装饰={request.decoration or ''}"
    save_demo_tune_record(
        tune_record_id=str(saved_tune.get("tune_id") or ""),
        root_tryon_record_id=str(root.get("record_id") or request.tryon_record_id),
        parent_tune_record_id=parent.get("tune_record_id") if parent else None,
        root_hand_id=str(root.get("hand_id") or request.hand_id or ""),
        root_style_id=str(root.get("style_id") or ""),
        root_tryon_image_url=str(root.get("result_image_url") or ""),
        input_image_url=request.style_image_url,
        output_image_url=tuned_image_url,
        operation_mode="single",
        operation_payload=operation_payload,
        operation_summary=operation_summary,
        generation_mode=generation_mode,
        created_at=str(saved_tune.get("created_at") or ""),
    )


def _extract_visible_tune_text(raw_text: str) -> str:
    text = str(raw_text or "").strip()
    if "用户原始需求：" in text:
        text = text.split("用户原始需求：", 1)[1]
    if "请将用户需求理解为" in text:
        text = text.split("请将用户需求理解为", 1)[0]
    text = text.strip().strip("。")
    return text[:24] if text else "文字描述"
