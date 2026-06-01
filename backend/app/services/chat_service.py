from __future__ import annotations

from uuid import uuid4

from app.prompts.chat import SYSTEM_PROMPT as CHAT_SYSTEM_PROMPT
from app.schemas.chat import ChatAnswer, ChatRecommendationItem, ChatRequest, ChatResponse
from app.services.business_db import list_recommendation_candidates
from app.services.hand_analyzer import get_hand_profile
from app.services.multimodal_client import (
    MultimodalModelError,
    generate_text_json_with_gemini,
    is_gemini_enabled,
)
from app.services.taxonomy_store import get_all_approved_tag_values, get_popular_style_tag_values

_conversation_store: dict[str, list[dict]] = {}
_MAX_HISTORY_MESSAGES = 10


def _load_history(conversation_id: str) -> list[dict]:
    return _conversation_store.get(conversation_id, [])


def _save_turn(conversation_id: str, query: str, response: ChatResponse) -> None:
    history = _conversation_store.setdefault(conversation_id, [])
    rec_names = [r.style_name for r in response.answer.recommendations[:4]]
    history.append({"role": "user", "content": query})
    history.append({"role": "assistant", "content": response.answer.scene_analysis, "recommendations": rec_names})
    if len(history) > _MAX_HISTORY_MESSAGES:
        _conversation_store[conversation_id] = history[-_MAX_HISTORY_MESSAGES:]


def _format_history(history: list[dict]) -> str:
    if not history:
        return ""
    lines = ["历史对话："]
    for msg in history:
        if msg["role"] == "user":
            lines.append(f"- 用户：{msg['content']}")
        else:
            recs = msg.get("recommendations", [])
            rec_note = f"（推荐了{'、'.join(recs)}）" if recs else ""
            lines.append(f"- 助手：{msg['content']}{rec_note}")
    return "\n".join(lines)


def chat(request: ChatRequest) -> ChatResponse:
    conversation_id = request.conversation_id or f"conv-{uuid4().hex[:8]}"
    history = _load_history(conversation_id) if request.conversation_id else []

    keywords = _extract_keywords(request.query)
    candidates = _search_styles(keywords, request, limit=8)

    if is_gemini_enabled():
        try:
            response = _generate_with_llm(conversation_id, request, candidates, history)
        except (MultimodalModelError, KeyError, TypeError, ValueError):
            response = _generate_mock(conversation_id, request, candidates, history)
    else:
        response = _generate_mock(conversation_id, request, candidates, history)

    _save_turn(conversation_id, request.query, response)
    return response


def _extract_keywords(query: str) -> set[str]:
    """Simple keyword extraction: intersect query text with approved taxonomy values."""
    approved = get_all_approved_tag_values()
    if not approved:
        approved = set(get_popular_style_tag_values(limit=30))
    return {tag for tag in approved if tag in query}


def _search_styles(keywords: set[str], request: ChatRequest, limit: int) -> list[dict]:
    scored = []
    for style in list_recommendation_candidates(limit=200):
        tags = _flatten_tags(style["tags"])
        matched = sorted(set(tags) & keywords) if keywords else []
        query_hits = sum(1 for tag in tags if request.query and tag in request.query)
        score = len(matched) * 12 + query_hits * 6 + float(style.get("hot_score") or 0) * 0.3
        scored.append((score, matched, style))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        {"style_id": s["style_id"], "style_name": s["style_name"], "image_url": s["enhanced_style_image_url"], "tags": s["tags"]}
        for _, _, s in scored[:limit]
    ]


def _generate_with_llm(conversation_id: str, request: ChatRequest, candidates: list[dict], history: list[dict]) -> ChatResponse:
    data = generate_text_json_with_gemini(
        system_prompt=CHAT_SYSTEM_PROMPT,
        user_prompt=_build_llm_prompt(request, candidates, history),
    )
    recs = [
        ChatRecommendationItem(
            style_id=item["style_id"],
            style_name=item["style_name"],
            image_url=item.get("image_url", ""),
            reason=item.get("reason", ""),
        )
        for item in data.get("recommendations", [])
        if isinstance(item, dict) and item.get("style_id")
    ]
    return ChatResponse(
        conversation_id=conversation_id,
        answer=ChatAnswer(
            scene_analysis=str(data.get("scene_analysis") or ""),
            recommendations=recs,
            tips=str(data.get("tips") or ""),
            follow_up=str(data.get("follow_up") or ""),
        ),
        suggested_questions=[str(q) for q in (data.get("suggested_questions") or [])],
        generation_mode="gemini-2.5-flash",
    )


def _generate_mock(conversation_id: str, request: ChatRequest, candidates: list[dict], history: list[dict]) -> ChatResponse:
    top4 = candidates[:4]
    recs = [
        ChatRecommendationItem(
            style_id=s["style_id"],
            style_name=s["style_name"],
            image_url=s["image_url"],
            reason=f"{s['style_name']}与你的需求匹配，适合当前场景。",
        )
        for s in top4
    ]
    skin_tone = _hand_context(request)
    tips = f"建议选择{skin_tone}友好的色系，避免过于夸张的款式。" if skin_tone else "建议根据肤色和手型选择适合的款式。"
    return ChatResponse(
        conversation_id=conversation_id,
        answer=ChatAnswer(
            scene_analysis=f"根据「{request.query}」为你找到以下推荐款式。",
            recommendations=recs,
            tips=tips,
            follow_up="想看看其他风格的美甲吗？",
        ),
        suggested_questions=["法式简约款有哪些？", "适合约会的款式推荐", "最近流行的美甲风格"],
        generation_mode="mock",
    )


def _build_llm_prompt(request: ChatRequest, candidates: list[dict], history: list[dict]) -> str:
    hand_note = _hand_context(request) or "用户未提供手部分析信息，仅根据问题推荐。"
    style_list = "\n".join(
        f"- {s['style_id']} | {s['style_name']} | 标签: {', '.join(_flatten_tags(s['tags'])[:8])}"
        for s in candidates
    )
    history_block = _format_history(history)
    return (
        f"{history_block}\n\n"
        f"用户问题：{request.query}\n"
        f"手部特征：{hand_note}\n"
        f"候选款式列表（只能从下面选）：\n{style_list}\n\n"
        "请输出JSON：\n"
        '{"scene_analysis":"结合用户问题和手部特征的简短分析，1-2句",'
        '"recommendations":[{"style_id":"必须从候选列表中选","style_name":"","image_url":"","reason":"结合手部特征的推荐理由"}],'
        '"tips":"额外搭配建议",'
        '"follow_up":"一个引导性问题，帮助用户继续探索",'
        '"suggested_questions":["推荐1-3个用户可能感兴趣的下一个问题"]}'
        "\n要求：recommendations选3-4款，reason须提及用户的手部特征或问题场景，follow_up要自然不生硬。"
        "如果历史对话中已推荐过某些款式，本轮应优先推荐不同的款式。"
    )


def _hand_context(request: ChatRequest) -> str | None:
    if not request.hand_profile_id:
        return None

    profile = get_hand_profile(request.hand_profile_id)
    if profile:
        return (
            f"肤色{profile.skin_tone}，手型{profile.hand_shape}，"
            f"推荐色系{', '.join(profile.recommended_colors[:4])}，"
            f"推荐风格{', '.join(profile.recommended_styles[:4])}，"
            f"推荐甲形{', '.join(profile.recommended_nail_shapes[:4])}"
        )
    return None


def _flatten_tags(tags: dict[str, list[str]]) -> list[str]:
    values: list[str] = []
    for tag_values in tags.values():
        if isinstance(tag_values, list):
            values.extend(tag_values)
        elif isinstance(tag_values, str) and tag_values:
            values.append(tag_values)
    return sorted(set(values))
