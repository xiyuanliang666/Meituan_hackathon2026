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
from app.services.multimodal_client import (
    MultimodalModelError,
    analyze_image_json_with_gemini,
    analyze_image_json_with_qwen_vl,
    is_gemini_enabled,
    is_qwen_vl_enabled,
)

_standardized_store: dict[str, str] = {}
_user_hands: dict[str, list[dict]] = {}


def get_standardized_hand(standardized_hand_id: str) -> str | None:
    return _standardized_store.get(standardized_hand_id)


def get_user_hand_status(user_id: str) -> dict:
    """Return the currently selected hand for backward-compatible quick lookup."""
    hands = _user_hands.get(user_id, [])
    selected = next((h for h in hands if h.get("selected")), None)
    if not selected and hands:
        selected = hands[0]
    if selected:
        return {
            "has_hand": True,
            "standardized_hand_id": selected["hand_id"],
            "standardized_image_url": selected["image_url"],
        }
    return {"has_hand": False, "standardized_hand_id": "", "standardized_image_url": ""}


def get_user_hands(user_id: str) -> UserHandsResponse:
    hands = _user_hands.get(user_id, [])
    return UserHandsResponse(
        user_id=user_id,
        hands=[UserHandItem(**h) for h in hands],
    )


def sync_user_hands(request: SyncHandsRequest) -> UserHandsResponse:
    selected_count = sum(1 for h in request.hands if h.selected)
    hands = [h.model_dump() for h in request.hands]

    if hands and selected_count != 1:
        hands[0]["selected"] = True
        for h in hands[1:]:
            h["selected"] = False

    _user_hands[request.user_id] = hands
    return UserHandsResponse(
        user_id=request.user_id,
        hands=[UserHandItem(**h) for h in hands],
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
    _standardized_store[hand_id] = image_url

    if request.user_id:
        existing = _user_hands.get(request.user_id, [])
        already_exists = any(h["hand_id"] == hand_id for h in existing)
        if not already_exists:
            is_first = len(existing) == 0
            existing.append({"hand_id": hand_id, "image_url": image_url, "selected": is_first})
            _user_hands[request.user_id] = existing

    has_nail_art = quality.get("nail_art_detected", False)
    note = "检测到已有美甲，已直接入库。" if has_nail_art else "手部图片符合标准，已入库。"

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
