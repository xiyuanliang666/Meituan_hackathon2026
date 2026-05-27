from app.data.nail_taxonomy_v2_seed import HAND_SHAPE_PROFILE_MAP, SKIN_TONE_PROFILE_MAP
from app.schemas.recommendation import RecommendationItem, RecommendationRequest, RecommendationResponse
from app.services.business_db import list_recommendation_candidates
from app.services.hand_analyzer import get_hand_profile
from app.services.multimodal_client import (
    MultimodalModelError,
    generate_text_json_with_gemini,
    is_gemini_enabled,
)
from app.services.taxonomy_store import get_all_approved_tag_values, get_popular_style_tag_values


def recommend_styles(request: RecommendationRequest) -> RecommendationResponse:
    constraints = _build_constraints(request)
    scored = []

    for style in list_recommendation_candidates():
        tags = _flatten_tags(style["tags"])
        matched = sorted(tags & constraints)
        query_hits = _query_hits(request.query, tags)
        business_score = _business_score(style)
        score = len(matched) * 12 + query_hits * 6 + business_score
        scored.append((score, matched, style))

    scored.sort(key=lambda item: item[0], reverse=True)
    top_styles = [(score, matched, style) for score, matched, style in scored[:request.limit]]

    hand_context = _load_hand_context(request)
    llm_reasons = _build_reasons_with_llm(top_styles, hand_context) if hand_context else {}

    items = []
    for score, matched, style in top_styles:
        reason = llm_reasons.get(
            style["style_id"],
            _build_template_reason(style, matched, request),
        )
        items.append(
            RecommendationItem(
                style_id=style["style_id"],
                style_name=style["style_name"],
                image_url=style["enhanced_style_image_url"],
                reason=reason,
                matched_tags=matched[:5],
                score=round(score, 2),
            )
        )
    return RecommendationResponse(recommendations=items)


def _load_hand_context(request: RecommendationRequest) -> dict | None:
    if not request.hand_profile_id:
        if request.skin_tone or request.hand_shape:
            return {
                "skin_tone": request.skin_tone or "unknown",
                "hand_shape": request.hand_shape or "unknown",
                "colors": [],
                "styles": [],
                "nail_shapes": [],
            }
        return None

    profile = get_hand_profile(request.hand_profile_id)
    if not profile:
        return None
    return {
        "skin_tone": profile.skin_tone,
        "hand_shape": profile.hand_shape,
        "colors": profile.recommended_colors[:4],
        "styles": profile.recommended_styles[:4],
        "nail_shapes": profile.recommended_nail_shapes[:4],
    }


def _build_reasons_with_llm(
    top_styles: list[tuple[float, list[str], dict]],
    hand_context: dict,
) -> dict[str, str]:
    if not is_gemini_enabled():
        return {}

    style_lines = "\n".join(
        f"- {s['style_id']} | {s['style_name']} | 标签: {', '.join(sorted(_flatten_tags(s['tags']))[:6])}"
        for _, _, s in top_styles
    )
    prompt = (
        f"你是美甲推荐顾问。根据用户的手部特征，为以下{len(top_styles)}款美甲款式各生成一句简短的推荐理由。\n\n"
        f"用户手部特征：\n"
        f"- 肤色：{hand_context['skin_tone']}\n"
        f"- 手型：{hand_context['hand_shape']}\n"
        f"- 推荐色系：{', '.join(hand_context['colors']) if hand_context['colors'] else '不限'}\n"
        f"- 推荐风格：{', '.join(hand_context['styles']) if hand_context['styles'] else '不限'}\n"
        f"- 推荐甲形：{', '.join(hand_context['nail_shapes']) if hand_context['nail_shapes'] else '不限'}\n\n"
        f"候选款式：\n{style_lines}\n\n"
        "请输出JSON：\n"
        '{"reasons":[{"style_id":"...","reason":"一句话推荐理由，15字以内，自然口语化"}]}\n\n'
        "要求：每条理由15字以内，必须结合用户肤色或手型特征，各款理由要有差异化，不要千篇一律。只输出合法JSON。"
    )

    try:
        data = generate_text_json_with_gemini(
            system_prompt="你是美甲推荐顾问。只输出合法JSON，不要输出Markdown。",
            user_prompt=prompt,
        )
        return {
            item["style_id"]: item["reason"]
            for item in data.get("reasons", [])
            if isinstance(item, dict) and item.get("style_id") and item.get("reason")
        }
    except (MultimodalModelError, KeyError, TypeError, ValueError):
        return {}


def _build_template_reason(style: dict, matched: list[str], request: RecommendationRequest) -> str:
    if matched:
        return f"{style['style_name']}命中{'、'.join(matched[:3])}等特征，适合当前手部特征和场景需求。"
    if request.query:
        return f"{style['style_name']}与「{request.query}」的风格诉求接近，可作为备选试戴款。"
    return f"{style['style_name']}当前热度分为{style.get('hot_score', 0):.0f}，适合作为默认推荐款。"


def _build_constraints(request: RecommendationRequest) -> set[str]:
    approved_tags = get_all_approved_tag_values()
    constraints: set[str] = set()

    if request.skin_tone:
        mapped = SKIN_TONE_PROFILE_MAP.get(request.skin_tone)
        if mapped and mapped in approved_tags:
            constraints.add(mapped)

    if request.hand_shape:
        mapped = HAND_SHAPE_PROFILE_MAP.get(request.hand_shape)
        if mapped and mapped in approved_tags:
            constraints.add(mapped)

    if request.query:
        for tag in approved_tags:
            if tag in request.query:
                constraints.add(tag)

    if not constraints:
        constraints = set(get_popular_style_tag_values(limit=6)) & approved_tags
    if not constraints:
        constraints = set(list(approved_tags)[:6])

    return constraints


def _query_hits(query: str | None, tags: set[str]) -> int:
    if not query:
        return 0
    return sum(1 for tag in tags if tag in query)


def _flatten_tags(tags: dict[str, list[str]]) -> set[str]:
    values: set[str] = set()
    for tag_values in tags.values():
        if isinstance(tag_values, list):
            values.update(tag_values)
        elif isinstance(tag_values, str) and tag_values:
            values.add(tag_values)
    return values


def _business_score(style: dict) -> float:
    signal_score = 0.0
    for signal in style.get("signals", []):
        value = float(signal["value"])
        weight = float(signal["weight"])
        if signal["signal"] == "试戴收藏率":
            value *= 100
        signal_score += value * weight
    hot_score = float(style.get("hot_score") or 0)
    life_cycle_bonus = {"上升期": 8, "峰值期": 5, "观察期": 2, "衰退期": -3}.get(style.get("life_cycle"), 0)
    return hot_score * 0.35 + signal_score * 0.45 + life_cycle_bonus
