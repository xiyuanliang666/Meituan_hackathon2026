from hashlib import sha1

from app.prompts.hand_analysis import (
    SYSTEM_PROMPT as HAND_ANALYSIS_SYSTEM_PROMPT,
    USER_PROMPT as HAND_ANALYSIS_USER_PROMPT,
)
from app.schemas.hand import AnalyzeHandRequest, HandProfileResponse
from app.services.business_db import (
    find_user_hand_profile,
    get_user_hand_asset_by_image,
    get_user_hand_profile,
    save_user_hand_profile,
    upsert_user_demo_state,
)
from app.services.multimodal_client import (
    MultimodalModelError,
    analyze_image_json_with_qwen_vl,
    is_qwen_vl_enabled,
)


def get_hand_profile(hand_profile_id: str) -> HandProfileResponse | None:
    payload = get_user_hand_profile(hand_profile_id)
    return HandProfileResponse(**payload) if payload else None


def analyze_hand(request: AnalyzeHandRequest) -> HandProfileResponse:
    digest = sha1(request.hand_image_url.encode("utf-8")).hexdigest()
    hand_profile_id = "hand-" + digest[:8]
    cached = find_user_hand_profile(request.user_id, request.hand_image_url, hand_profile_id=hand_profile_id)
    if cached:
        return HandProfileResponse(**cached)

    if is_qwen_vl_enabled():
        try:
            result = _analyze_hand_with_model(request)
        except MultimodalModelError:
            result = _analyze_hand_mock(request)
    else:
        result = _analyze_hand_mock(request)
    hand_asset = get_user_hand_asset_by_image(request.user_id, request.hand_image_url) if request.user_id else None
    saved = save_user_hand_profile(
        hand_profile_id=result.hand_profile_id,
        user_id=request.user_id,
        hand_id=hand_asset.get("hand_id") if hand_asset else None,
        hand_image_url=request.hand_image_url,
        skin_tone=result.skin_tone,
        hand_shape=result.hand_shape,
        recommended_colors=result.recommended_colors,
        recommended_styles=result.recommended_styles,
        recommended_nail_shapes=result.recommended_nail_shapes,
        analysis_reason=result.analysis_reason,
        analysis_mode=result.analysis_mode,
    )
    if request.user_id:
        upsert_user_demo_state(request.user_id, current_hand_profile_id=result.hand_profile_id)
    return HandProfileResponse(**saved)


def analyze_seed_hand_templates(limit: int | None = None) -> dict[str, object]:
    from app.services.business_db import (
        init_db,
        list_seed_hand_templates,
        update_hand_template_analysis,
    )

    init_db(seed=True)
    templates = list_seed_hand_templates(limit=limit)
    analyzed = 0
    failed = 0
    modes: dict[str, int] = {}
    skin_tones: dict[str, int] = {}

    for template in templates:
        try:
            profile = analyze_hand(
                AnalyzeHandRequest(
                    user_id="template-analysis",
                    hand_image_url=template["hand_image_url"],
                )
            )
            update_hand_template_analysis(
                template_id=template["hand_template_id"],
                skin_tone=profile.skin_tone,
                hand_shape=profile.hand_shape,
                recommended_colors=profile.recommended_colors,
                recommended_styles=profile.recommended_styles,
                recommended_nail_shapes=profile.recommended_nail_shapes,
                analysis_reason=profile.analysis_reason,
                analysis_mode=profile.analysis_mode,
            )
            analyzed += 1
            modes[profile.analysis_mode] = modes.get(profile.analysis_mode, 0) + 1
            skin_tones[profile.skin_tone] = skin_tones.get(profile.skin_tone, 0) + 1
        except Exception:
            failed += 1

    return {
        "total_templates": len(templates),
        "analyzed_templates": analyzed,
        "failed_templates": failed,
        "analysis_modes": modes,
        "skin_tones": skin_tones,
    }


def _analyze_hand_with_model(request: AnalyzeHandRequest) -> HandProfileResponse:
    data = analyze_image_json_with_qwen_vl(
        image_url=request.hand_image_url,
        system_prompt=HAND_ANALYSIS_SYSTEM_PROMPT,
        user_prompt=HAND_ANALYSIS_USER_PROMPT,
    )
    digest = sha1(request.hand_image_url.encode("utf-8")).hexdigest()
    return HandProfileResponse(
        hand_profile_id="hand-" + digest[:8],
        user_id=request.user_id,
        skin_tone=_as_enum(data.get("skin_tone"), {"冷白", "自然肤", "暖黄", "深肤", "unknown"}, "unknown"),
        hand_shape=_as_enum(data.get("hand_shape"), {"修长", "标准", "短宽", "unknown"}, "unknown"),
        recommended_colors=_as_str_list(data.get("recommended_colors")),
        recommended_styles=_as_str_list(data.get("recommended_styles")),
        recommended_nail_shapes=_as_str_list(data.get("recommended_nail_shapes")),
        analysis_reason=str(data.get("analysis_reason") or "已完成手部特征分析。"),
        analysis_mode="qwen-vl-plus",
    )


def _analyze_hand_mock(request: AnalyzeHandRequest) -> HandProfileResponse:
    """Analyze a hand image with deterministic demo output."""
    digest = sha1(request.hand_image_url.encode("utf-8")).hexdigest()
    bucket = int(digest[:2], 16) % 3

    if bucket == 0:
        skin_tone = "暖黄"
        hand_shape = "短宽"
        colors = ["奶油白", "豆沙粉", "玫瑰金"]
        styles = ["显白", "纵向延伸", "简约", "渐变"]
        nail_shapes = ["方圆甲", "椭圆甲"]
        reason = "肤色偏暖，低饱和暖色更显白；手指比例偏短，适合纵向渐变和留白设计。"
    elif bucket == 1:
        skin_tone = "自然肤"
        hand_shape = "标准"
        colors = ["裸粉", "奶茶色", "酒红"]
        styles = ["通勤", "法式", "细闪"]
        nail_shapes = ["方圆甲", "圆甲"]
        reason = "自然肤色适配范围较广，标准手型可以优先选择通勤法式和细闪款。"
    else:
        skin_tone = "冷白"
        hand_shape = "修长"
        colors = ["蓝色", "银色", "正红"]
        styles = ["冷感", "镜面", "复杂装饰"]
        nail_shapes = ["椭圆甲", "尖甲"]
        reason = "冷白肤色适合冷调和高对比色，修长手型可以承接更强装饰感的款式。"

    return HandProfileResponse(
        hand_profile_id="hand-" + digest[:8],
        user_id=request.user_id,
        skin_tone=skin_tone,
        hand_shape=hand_shape,
        recommended_colors=colors,
        recommended_styles=styles,
        recommended_nail_shapes=nail_shapes,
        analysis_reason=reason,
        analysis_mode="mock",
    )


def _as_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _as_enum(value: object, allowed: set[str], default: str) -> str:
    text = str(value).strip() if value is not None else ""
    return text if text in allowed else default
