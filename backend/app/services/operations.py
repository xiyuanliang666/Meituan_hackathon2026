import json

from app.schemas.operations import (
    AuditPushCardRequest,
    AuditPushCardResponse,
    PushCardResponse,
    ReportRequest,
    ReportResponse,
    SkillExecuteRequest,
    SkillExecuteResponse,
    Suggestion,
)
from app.services.business_db import list_event_stats, list_hot_push_candidates, upsert_push_audit
from app.services.multimodal_client import (
    MultimodalModelError,
    generate_text_json_with_gemini,
    is_gemini_enabled,
)


def list_push_cards() -> list[PushCardResponse]:
    return [PushCardResponse(**_push_card_from_candidate(item)) for item in list_hot_push_candidates(limit=8)]


def audit_push_card(push_id: str, request: AuditPushCardRequest) -> AuditPushCardResponse:
    candidates = {item["push_id"]: item for item in list_hot_push_candidates(limit=50)}
    candidate = candidates.get(push_id)
    if not candidate:
        return AuditPushCardResponse(
            success=False,
            push_id=push_id,
            style_id="",
            status="not_found",
            message="推送卡片不存在",
        )

    status = "published" if request.action == "accepted" else "rejected"
    upsert_push_audit(push_id=push_id, style_id=candidate["style_id"], merchant_id=request.merchant_id, status=status)
    message = "已模拟上架并开通 AI 试戴入口" if status == "published" else "已归档该爆款推送"
    return AuditPushCardResponse(
        success=True,
        push_id=push_id,
        style_id=candidate["style_id"],
        status=status,
        message=message,
    )


def generate_report(request: ReportRequest) -> ReportResponse:
    context = _report_context_from_db(request)
    if is_gemini_enabled():
        try:
            return _generate_report_with_gemini(context)
        except (MultimodalModelError, KeyError, TypeError, ValueError):
            return _generate_report_mock(context)
    return _generate_report_mock(context)


def _generate_report_with_gemini(context: dict) -> ReportResponse:
    data = generate_text_json_with_gemini(
        system_prompt=(
            "你是美团本地生活美甲商户运营助手。只输出合法 JSON，不要输出 Markdown。"
            "请基于经营数据生成简洁、可执行、适合商户阅读的复盘报告和运营建议。"
            "字段名使用英文，面向商户展示的字段值和文案必须使用中文。"
        ),
        user_prompt=(
            "请输出字段 report_summary:string, suggestions:array。"
            "每条 suggestion 必须包含 text:string, action_type:string, "
            "action_params:object, requires_confirm:boolean, adopted:boolean。"
            "action_type 只能从 take_down_style, publish_style, boost_budget, "
            "pause_budget, prepare_replacement, maintain_strategy 中选择。"
            f"\n输入数据：{json.dumps(context, ensure_ascii=False)}"
        ),
    )
    suggestions = [
        Suggestion(
            text=str(item.get("text") or ""),
            action_type=str(item.get("action_type") or "maintain_strategy"),
            action_params=item.get("action_params") if isinstance(item.get("action_params"), dict) else {},
            requires_confirm=bool(item.get("requires_confirm", False)),
            adopted=bool(item.get("adopted", False)),
        )
        for item in data.get("suggestions", [])
        if isinstance(item, dict) and item.get("text")
    ]
    if not suggestions:
        raise ValueError("Gemini report has no valid suggestions")
    return ReportResponse(
        report_summary=str(data.get("report_summary") or "已生成本期运营复盘。"),
        suggestions=suggestions,
        generation_mode="gemini-2.5-flash",
    )


def _generate_report_mock(context: dict) -> ReportResponse:
    current = context["current_period"]
    last = context["last_period"]
    hot_styles = context["hot_styles"]
    event_stats = context["event_stats"]

    try_delta = _delta(current.get("try_rate"), last.get("try_rate"))
    fav_delta = _delta(current.get("favorite_rate"), last.get("favorite_rate"))
    order_delta = _delta(current.get("order_rate"), last.get("order_rate"))
    top_style = hot_styles[0] if hot_styles else {"name": "核心款式", "style_id": "", "life_cycle": "观察期", "score": 0}
    top_event_style = event_stats[0] if event_stats else None

    return ReportResponse(
        report_summary=(
            f"本期试戴率较上期变化{try_delta}，收藏率变化{fav_delta}，下单率变化{order_delta}。"
            f"{top_style['name']}当前热度分{top_style['score']:.0f}，处于{top_style['life_cycle']}。"
            f"{_event_summary(top_event_style)}"
        ),
        suggestions=[
            Suggestion(
                text=f"{top_style['name']}热度靠前，建议优先上架主推并加大投流预算 20%。",
                action_type="boost_budget",
                action_params={"style_id": top_style["style_id"], "budget_delta": 0.20},
                requires_confirm=True,
            ),
            Suggestion(
                text="对试戴点击低但曝光高的款式，建议降低主推权重，保留自然流量观察。",
                action_type="maintain_strategy",
                action_params={"reason": "wait_for_more_events"},
                requires_confirm=False,
            ),
            Suggestion(
                text="建议继续积累曝光、试戴、收藏和下单事件，用行为数据校准爆款识别权重。",
                action_type="prepare_replacement",
                action_params={"target_event_count": 50},
                requires_confirm=False,
            ),
        ],
        generation_mode="db_mock",
    )


def execute_skill(request: SkillExecuteRequest) -> SkillExecuteResponse:
    action = request.action_type
    params = request.action_params

    messages = {
        "take_down_style": "已模拟下架款式",
        "publish_style": "已模拟上架款式",
        "boost_budget": "已模拟提高投流预算",
        "pause_budget": "已模拟收缩投流预算",
        "prepare_replacement": "已模拟进入替换款准备流程",
        "maintain_strategy": "已记录维持当前策略",
        "notify_complete": "操作完成通知已发送",
    }
    if action not in messages:
        return SkillExecuteResponse(
            success=False,
            action_type=action,
            message="未知 action_type",
            state_patch={},
        )

    return SkillExecuteResponse(
        success=True,
        action_type=action,
        message=messages[action],
        state_patch={"action_params": params, "adopted": True},
    )


def _push_card_from_candidate(candidate: dict) -> dict:
    style_tags = _flatten_tags(candidate["tags"])
    event_stats = candidate.get("event_stats", {})
    signal_sources = _signal_sources_with_events(candidate["signals"], event_stats)
    hot_score = _hot_score(candidate, signal_sources)
    return {
        "push_id": candidate["push_id"],
        "style_id": candidate["style_id"],
        "style_name": candidate["style_name"],
        "style_tags": style_tags,
        "style_image_urls": [candidate["enhanced_style_image_url"]],
        "signal_sources": signal_sources,
        "hot_score": hot_score,
        "life_cycle": _life_cycle(candidate["life_cycle"], hot_score, event_stats),
        "life_cycle_trend": _mock_trend(hot_score),
        "coupon_url": f"https://i.meituan.com/coupon/{candidate['style_id']}",
        "coupon_price": _coupon_price(candidate["style_id"]),
        "tagline": _tagline(candidate["style_name"], style_tags),
        "status": candidate.get("status", "pending"),
    }


def _flatten_tags(tags: dict[str, list[str]]) -> list[str]:
    values: list[str] = []
    for tag_values in tags.values():
        values.extend(tag_values)
    return sorted(set(values))


def _signal_sources_with_events(signals: list[dict], event_stats: dict[str, int]) -> list[dict]:
    output = [
        {
            "signal": item["signal"],
            "value": float(item["value"]),
            "delta": float(item["delta"]),
            "weight": float(item["weight"]),
        }
        for item in signals
    ]
    try_on = event_stats.get("try_on", 0)
    favorite = event_stats.get("favorite", 0)
    order = event_stats.get("order", 0)
    if try_on or favorite or order:
        output.append(
            {
                "signal": "实时行为",
                "value": float(try_on * 3 + favorite * 6 + order * 12),
                "delta": 0.20,
                "weight": 0.20,
            }
        )
    return output


def _hot_score(candidate: dict, signal_sources: list[dict]) -> float:
    weighted = 0.0
    total_weight = 0.0
    for signal in signal_sources:
        value = signal["value"] * 100 if signal["signal"] == "试戴收藏率" else signal["value"]
        weighted += value * signal["weight"]
        total_weight += signal["weight"]
    base = candidate.get("hot_score") or 0
    score = base * 0.4 + (weighted / total_weight if total_weight else 0) * 0.6
    return round(min(score, 99.0), 2)


def _life_cycle(seed_life_cycle: str, hot_score: float, event_stats: dict[str, int]) -> str:
    if event_stats.get("try_on", 0) >= 3 or hot_score >= 85:
        return "上升期"
    return seed_life_cycle


def _mock_trend(hot_score: float) -> list[float]:
    start = max(10.0, hot_score - 28)
    return [round(start + (hot_score - start) * index / 11, 2) for index in range(12)]


def _coupon_price(style_id: str) -> float:
    suffix = int(style_id[-3:])
    return float(128 + (suffix % 5) * 20)


def _tagline(style_name: str, style_tags: list[str]) -> str:
    tags = "、".join(style_tags[:3]) or "高潜款式"
    return f"{style_name}近期{tags}相关热度较高，适合上架主推并开启 AI 试戴。"


def _report_context_from_db(request: ReportRequest) -> dict:
    push_cards = list_push_cards()
    event_stats = list_event_stats(limit=8)

    current_period = request.current_period or _period_from_event_stats(event_stats)
    last_period = request.last_period or {
        "try_rate": round(current_period["try_rate"] * 0.92, 4),
        "favorite_rate": round(current_period["favorite_rate"] * 0.88, 4),
        "order_rate": round(current_period["order_rate"] * 0.9, 4),
    }
    hot_styles = request.hot_styles or [
        {
            "style_id": card.style_id,
            "name": card.style_name,
            "life_cycle": card.life_cycle,
            "score": card.hot_score,
            "status": card.status,
        }
        for card in push_cards[:5]
    ]

    return {
        "merchant_id": request.merchant_id,
        "period": request.period,
        "merchant_prefs": request.merchant_prefs,
        "current_period": current_period,
        "last_period": last_period,
        "hot_styles": hot_styles,
        "event_stats": event_stats,
        "push_cards": [card.model_dump() for card in push_cards[:5]],
    }


def _period_from_event_stats(event_stats: list[dict]) -> dict:
    exposure_count = sum(item.get("exposure_count", 0) for item in event_stats)
    try_on_count = sum(item.get("try_on_count", 0) for item in event_stats)
    favorite_count = sum(item.get("favorite_count", 0) for item in event_stats)
    order_count = sum(item.get("order_count", 0) for item in event_stats)
    return {
        "exposure_count": exposure_count,
        "try_on_count": try_on_count,
        "favorite_count": favorite_count,
        "order_count": order_count,
        "try_rate": _rate(try_on_count, exposure_count, default=0.38),
        "favorite_rate": _rate(favorite_count, try_on_count, default=0.22),
        "order_rate": _rate(order_count, try_on_count, default=0.09),
    }


def _rate(numerator: int, denominator: int, default: float) -> float:
    if denominator <= 0:
        return default
    return round(numerator / denominator, 4)


def _event_summary(item: dict | None) -> str:
    if not item:
        return "当前真实行为样本较少，建议先通过 Demo 埋点积累试戴和收藏数据。"
    return (
        f"{item['style_name']}已有{item['try_on_count']}次试戴、"
        f"{item['favorite_count']}次收藏，可作为行为反馈样本继续观察。"
    )


def _delta(current: float | None, last: float | None) -> str:
    if current is None or last in (None, 0):
        return "暂无可比数据"
    value = (current - last) / last
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.1%}"
