from __future__ import annotations

from hashlib import sha1

from app.prompts.hand_quality import (
    SYSTEM_PROMPT as QUALITY_SYSTEM_PROMPT,
    USER_PROMPT as QUALITY_USER_PROMPT,
)
from app.schemas.hand_standardize import (
    QualityDetails,
    StandardizeHandRequest,
    StandardizeHandResponse,
    SyncHandsRequest,
    UserHandItem,
    UserHandsResponse,
)
from app.services.business_db import (
    get_user_hand_asset,
    get_selected_user_hand_asset,
    list_user_hand_assets,
    save_user_hand_asset,
    sync_user_hand_assets,
    upsert_user_demo_state,
)
from app.services.multimodal_client import (
    MultimodalModelError,
    analyze_image_json_with_gemini,
    analyze_image_json_with_qwen_vl,
    is_gemini_enabled,
    is_qwen_vl_enabled,
)


def get_standardized_hand(standardized_hand_id: str) -> str | None:
    item = get_user_hand_asset(standardized_hand_id)
    return str(item.get("image_url")) if item else None


def get_user_hand_status(user_id: str) -> dict:
    """Return the currently selected hand for backward-compatible quick lookup."""
    selected = get_selected_user_hand_asset(user_id)
    if selected:
        return {
            "has_hand": True,
            "standardized_hand_id": selected["hand_id"],
            "standardized_image_url": selected["image_url"],
        }
    return {"has_hand": False, "standardized_hand_id": "", "standardized_image_url": ""}


def get_user_hands(user_id: str) -> UserHandsResponse:
    hands = list_user_hand_assets(user_id)
    return UserHandsResponse(
        user_id=user_id,
        hands=[UserHandItem(hand_id=h["hand_id"], image_url=h["image_url"], selected=h["selected"]) for h in hands],
    )


def sync_user_hands(request: SyncHandsRequest) -> UserHandsResponse:
    selected_count = sum(1 for h in request.hands if h.selected)
    hands = [h.model_dump() for h in request.hands]
    if hands and selected_count != 1:
        hands[0]["selected"] = True
        for item in hands[1:]:
            item["selected"] = False
    synced = sync_user_hand_assets(request.user_id, hands)
    selected = next((item for item in synced if item["selected"]), None)
    if selected:
        upsert_user_demo_state(request.user_id, current_hand_id=selected["hand_id"])
    return UserHandsResponse(
        user_id=request.user_id,
        hands=[UserHandItem(hand_id=h["hand_id"], image_url=h["image_url"], selected=h["selected"]) for h in synced],
    )


def standardize_hand(request: StandardizeHandRequest) -> StandardizeHandResponse:
    image_url = request.hand_image_url
    quality = _run_quality_check(image_url)

    if not quality["quality_pass"]:
        return StandardizeHandResponse(
            standardized_hand_id="",
            standardized_image_url=image_url,
            quality_pass=False,
            quality_details=QualityDetails(
                fingers_up=quality.get("fingers_up", False),
                full_hand_visible=quality.get("full_hand_visible", False),
                fingers_spread=quality.get("fingers_spread", False),
                bright_lighting=quality.get("bright_lighting", False),
                clean_background=quality.get("clean_background", False),
            ),
            quality_issues=quality.get("issues", []),
            nail_art_detected=quality.get("nail_art_detected", False),
            processing_note="图片不符合质量标准，请重新拍摄上传。",
        )

    hand_id = "hand-" + sha1(image_url.encode("utf-8")).hexdigest()[:10]
    has_nail_art = quality.get("nail_art_detected", False)
    note = "检测到已有美甲，已直接入库。" if has_nail_art else "手部图片符合标准，已入库。"
    if request.user_id:
        selected = get_selected_user_hand_asset(request.user_id) is None
        saved = save_user_hand_asset(
            request.user_id,
            hand_id,
            image_url,
            selected=selected,
            quality_pass=True,
            quality_issues=[],
            nail_art_detected=has_nail_art,
            processing_note=note,
        )
        if saved["selected"]:
            upsert_user_demo_state(request.user_id, current_hand_id=hand_id)

    return StandardizeHandResponse(
        standardized_hand_id=hand_id,
        standardized_image_url=image_url,
        quality_pass=True,
        quality_details=QualityDetails(
            fingers_up=quality.get("fingers_up", False),
            full_hand_visible=quality.get("full_hand_visible", False),
            fingers_spread=quality.get("fingers_spread", False),
            bright_lighting=quality.get("bright_lighting", False),
            clean_background=quality.get("clean_background", False),
        ),
        quality_issues=quality.get("issues", []),
        nail_art_detected=has_nail_art,
        processing_note=note,
    )


def _run_quality_check(image_url: str) -> dict:
    if is_gemini_enabled():
        try:
            return analyze_image_json_with_gemini(
                image_url=image_url,
                system_prompt=QUALITY_SYSTEM_PROMPT,
                user_prompt=QUALITY_USER_PROMPT,
            )
        except MultimodalModelError:
            pass

    if is_qwen_vl_enabled():
        try:
            return analyze_image_json_with_qwen_vl(
                image_url=image_url,
                system_prompt=QUALITY_SYSTEM_PROMPT,
                user_prompt=QUALITY_USER_PROMPT,
            )
        except MultimodalModelError:
            pass

    return {
        "quality_pass": True,
        "fingers_up": True,
        "full_hand_visible": True,
        "fingers_spread": True,
        "bright_lighting": True,
        "clean_background": True,
        "issues": [],
        "nail_art_detected": False,
    }
