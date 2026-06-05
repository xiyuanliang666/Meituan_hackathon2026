import json
from pathlib import Path

from app.prompts.operations import SYSTEM_PROMPT as OPERATIONS_SYSTEM_PROMPT
from app.config import get_settings
from app.schemas.operations import (
    AuditPushCardRequest,
    AuditPushCardResponse,
    PendingPushStylesRequest,
    PendingPushStylesResponse,
    PushCardResponse,
    ReportHotStyleItem,
    ReportMetric,
    ReportRequest,
    ReportResponse,
    SkillExecuteRequest,
    SkillExecuteResponse,
    Suggestion,
)
from app.services.business_db import (
    create_report_snapshot,
    list_event_stats,
    list_hot_push_candidates,
    list_styles,
    set_pending_push_styles,
    upsert_push_audit,
)
from app.services.multimodal_client import (
    MultimodalModelError,
    generate_text_json_with_gemini,
    is_gemini_enabled,
)

TAG_DISPLAY_ORDER = (
    "style_tags",
    "color_system",
    "nail_technique",
    "nail_decoration",
    "nail_finish",
    "nail_shape",
    "nail_length",
    "scene_tags",
    "season_tags",
)

DEMO_PUSH_SIGNAL_OVERRIDES: dict[str, dict[str, object]] = {
    "push-b38bf71ae1": {
        "hot_score": 93.0,
        "life_cycle": "上升期",
        "signals": [
            {"signal": "搜索热度", "value": 92.0, "delta": 0.24, "weight": 0.30},
            {"signal": "评价词频", "value": 218.0, "delta": 0.17, "weight": 0.30},
            {"signal": "试戴收藏率", "value": 0.43, "delta": 0.28, "weight": 0.40},
        ],
    },
    "push-b567a4e3b0": {
        "hot_score": 88.0,
        "life_cycle": "峰值期",
        "signals": [
            {"signal": "搜索热度", "value": 84.0, "delta": 0.19, "weight": 0.30},
            {"signal": "评价词频", "value": 176.0, "delta": 0.12, "weight": 0.30},
            {"signal": "试戴收藏率", "value": 0.37, "delta": 0.21, "weight": 0.40},
        ],
    },
    "push-ca2ef69375": {
        "hot_score": 79.0,
        "life_cycle": "上升期",
        "signals": [
            {"signal": "搜索热度", "value": 77.0, "delta": 0.11, "weight": 0.30},
            {"signal": "评价词频", "value": 142.0, "delta": 0.09, "weight": 0.30},
            {"signal": "试戴收藏率", "value": 0.31, "delta": 0.16, "weight": 0.40},
        ],
    },
}


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
    audit_record = upsert_push_audit(
        push_id=push_id,
        style_id=candidate["style_id"],
        merchant_id=request.merchant_id,
        status=status,
        selected_image_url=request.selected_image_url or candidate["enhanced_style_image_url"],
        selected_coupon_url=request.selected_coupon_url or f"https://i.meituan.com/coupon/{candidate['style_id']}",
        final_tagline=request.final_tagline or _tagline(candidate["style_name"], _flatten_tags(candidate["tags"])),
        final_price=request.final_price if request.final_price is not None else _coupon_price(candidate["style_id"]),
    )
    message = "已模拟上架并开通 AI 试戴入口" if status == "published" else "已归档该爆款推送"
    return AuditPushCardResponse(
        success=True,
        push_id=push_id,
        style_id=candidate["style_id"],
        status=status,
        message=message,
        selected_image_url=audit_record.get("selected_image_url"),
        selected_coupon_url=audit_record.get("selected_coupon_url"),
        final_tagline=audit_record.get("final_tagline"),
        final_price=audit_record.get("final_price"),
    )


def update_pending_push_styles(request: PendingPushStylesRequest) -> PendingPushStylesResponse:
    result = set_pending_push_styles(
        style_ids=request.style_ids,
        merchant_id=request.merchant_id,
        replace_pending=request.replace_pending,
    )
    return PendingPushStylesResponse(**result)


def generate_report(request: ReportRequest) -> ReportResponse:
    context = _report_context_from_db(request)
    if is_gemini_enabled():
        try:
            response = _generate_report_with_gemini(context)
            return _persist_report_response(context, response)
        except (MultimodalModelError, KeyError, TypeError, ValueError):
            response = _generate_report_mock(context)
            return _persist_report_response(context, response)
    response = _generate_report_mock(context)
    return _persist_report_response(context, response)


def _generate_report_with_gemini(context: dict) -> ReportResponse:
    data = generate_text_json_with_gemini(
        system_prompt=OPERATIONS_SYSTEM_PROMPT,
        user_prompt=(
            "请输出字段 report_summary:string, suggestions:array。"
            "每条 suggestion 必须包含 text:string, action_type:string, "
            "action_params:object, requires_confirm:boolean, adopted:boolean。"
            "action_type 只能从 take_down_style, publish_style, boost_budget, "
            "pause_budget, prepare_replacement, maintain_strategy 中选择。"
            f"\n输入数据：{json.dumps(context, ensure_ascii=False)}"
        ),
    )
    return ReportResponse(
        report_summary=str(data.get("report_summary") or "已生成本期运营复盘。"),
        suggestions=_fixed_report_suggestions(context),
        generation_mode="gemini-2.5-flash",
        period_label=context["period_label"],
        metrics=[ReportMetric(**item) for item in context["metrics"]],
        hot_styles=[ReportHotStyleItem(**item) for item in context["hot_style_cards"]],
        merchant_prefs=context["merchant_prefs"],
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
        suggestions=_fixed_report_suggestions(context),
        generation_mode="db_mock",
        period_label=context["period_label"],
        metrics=[ReportMetric(**item) for item in context["metrics"]],
        hot_styles=[ReportHotStyleItem(**item) for item in context["hot_style_cards"]],
        merchant_prefs=context["merchant_prefs"],
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


def _fixed_report_suggestions(context: dict) -> list[Suggestion]:
    pending_push_cards = [
        card for card in context.get("push_cards", [])
        if str(card.get("status") or "") not in {"accepted", "listed", "published"}
    ]
    pending_style_ids = {str(card.get("style_id") or "") for card in pending_push_cards}
    active_styles = list_styles(limit=20, status="active")
    active_style = next(
        (item for item in active_styles if item.get("style_id") not in pending_style_ids),
        active_styles[0] if active_styles else None,
    )
    pending_push = pending_push_cards[0] if pending_push_cards else None

    boost_style_name = (
        str(active_style.get("style_name") or "").strip()
        if isinstance(active_style, dict) else ""
    ) or "当前主推款式"
    boost_style_id = (
        str(active_style.get("style_id") or "").strip()
        if isinstance(active_style, dict) else ""
    )
    publish_style_name = (
        str(pending_push.get("style_name") or "").strip()
        if isinstance(pending_push, dict) else ""
    ) or "待上架新款式"
    publish_style_id = (
        str(pending_push.get("style_id") or "").strip()
        if isinstance(pending_push, dict) else ""
    )
    publish_push_id = (
        str(pending_push.get("push_id") or "").strip()
        if isinstance(pending_push, dict) else ""
    )

    return [
        Suggestion(
            text=f"{boost_style_name}热度较高，建议增加投流预算 20%。",
            action_type="boost_budget",
            action_params={
                "style_id": boost_style_id,
                "style_name": boost_style_name,
                "budget_from": 500,
                "budget_to": 600,
                "budget_delta": 0.20,
            },
            requires_confirm=True,
        ),
        Suggestion(
            text="当前整体投流 ROI 表现稳定，建议维持当前策略，继续观察自然流量与转化表现。",
            action_type="maintain_strategy",
            action_params={"reason": "keep_current_strategy"},
            requires_confirm=False,
        ),
        Suggestion(
            text=f"{publish_style_name}热度较高，建议上架新款式并加入当前主推。",
            action_type="publish_style",
            action_params={
                "push_id": publish_push_id,
                "style_id": publish_style_id,
                "style_name": publish_style_name,
            },
            requires_confirm=False,
        ),
    ]


def _push_card_from_candidate(candidate: dict) -> dict:
    override = DEMO_PUSH_SIGNAL_OVERRIDES.get(candidate["push_id"])
    if override:
        candidate = {
            **candidate,
            "hot_score": override["hot_score"],
            "life_cycle": override["life_cycle"],
            "signals": override["signals"],
        }
    style_tags = _flatten_tags(candidate["tags"])
    event_stats = candidate.get("event_stats", {})
    signal_sources = _signal_sources_with_events(candidate["signals"], event_stats)
    hot_score = _hot_score(candidate, signal_sources)
    push_id = candidate["push_id"]
    style_image_urls = [candidate["enhanced_style_image_url"], *_load_demo_composite_urls(push_id)]
    return {
        "push_id": push_id,
        "style_id": candidate["style_id"],
        "style_name": candidate["style_name"],
        "style_tags": style_tags,
        "style_image_urls": style_image_urls,
        "source_posts": _load_demo_source_posts(push_id),
        "signal_sources": signal_sources,
        "hot_score": hot_score,
        "life_cycle": _life_cycle(candidate["life_cycle"], hot_score, event_stats),
        "life_cycle_trend": _mock_trend(hot_score),
        "coupon_url": f"https://i.meituan.com/coupon/{candidate['style_id']}",
        "coupon_price": _coupon_price(candidate["style_id"]),
        "tagline": _tagline(candidate["style_name"], style_tags),
        "status": candidate.get("status", "pending"),
        "audit_details": candidate.get("audit_details", {}),
    }


def _load_demo_composite_urls(push_id: str) -> list[str]:
    folder = _demo_asset_root() / "push-composites"
    if not folder.exists():
        return []
    files = sorted(folder.glob(f"{push_id}__composite-*.*"))
    return [_demo_static_url("demo_assets/push-composites", file.name) for file in files]


def _load_demo_source_posts(push_id: str) -> list[dict]:
    folder = _demo_asset_root() / "push-sources"
    if not folder.exists():
        return []

    manifest_path = folder / f"{push_id}__sources.json"
    if manifest_path.exists():
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        source_posts = data.get("sources", []) if isinstance(data, dict) else []
        output: list[dict] = []
        for item in source_posts:
            if not isinstance(item, dict):
                continue
            resolved = dict(item)
            image_name = str(item.get("image") or "").strip()
            resolved["image_url"] = _demo_static_url("demo_assets/push-sources", image_name) if image_name else ""
            output.append(resolved)
        return output

    files = sorted(folder.glob(f"{push_id}__source-*.*"))
    return [
        {
            "image": file.name,
            "image_url": _demo_static_url("demo_assets/push-sources", file.name),
        }
        for file in files
    ]


def _demo_asset_root() -> Path:
    settings = get_settings()
    storage_dir = Path(settings.storage_dir)
    if not storage_dir.is_absolute():
        storage_dir = Path(__file__).resolve().parents[2] / storage_dir
    return storage_dir / "demo_assets"


def _demo_static_url(*parts: str) -> str:
    base = get_settings().public_base_url.rstrip("/")
    path = "/".join(part.strip("/").replace("\\", "/") for part in parts if part)
    return f"{base}/{path}"


def _flatten_tags(tags: dict[str, list[str] | str]) -> list[str]:
    values: list[str] = []
    for key in TAG_DISPLAY_ORDER:
        values.extend(_tag_values(tags.get(key)))
    for key, tag_values in tags.items():
        if key not in TAG_DISPLAY_ORDER:
            values.extend(_tag_values(tag_values))

    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        if value and value != "unknown" and value not in seen:
            seen.add(value)
            unique_values.append(value)
    return unique_values


def _tag_values(raw: list[str] | str | None) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        value = raw.strip()
        return [value] if value else []
    return [str(value).strip() for value in raw if str(value).strip()]


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
    digits = "".join(ch for ch in style_id if ch.isdigit())
    suffix = int(digits[-3:]) if digits else sum(ord(ch) for ch in style_id) % 1000
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
    metrics = _report_metrics(request.period, current_period, last_period)
    hot_style_cards = [_hot_style_item(card) for card in push_cards[:3]]

    return {
        "merchant_id": request.merchant_id,
        "period": request.period,
        "merchant_prefs": request.merchant_prefs,
        "period_label": _period_label(request.period),
        "current_period": current_period,
        "last_period": last_period,
        "hot_styles": hot_styles,
        "metrics": metrics,
        "hot_style_cards": hot_style_cards,
        "event_stats": event_stats,
        "push_cards": [card.model_dump() for card in push_cards[:5]],
    }


def _persist_report_response(context: dict[str, object], response: ReportResponse) -> ReportResponse:
    snapshot = create_report_snapshot(
        merchant_id=str(context.get("merchant_id") or ""),
        period=str(context.get("period") or "this_week"),
        merchant_prefs=response.merchant_prefs,
        current_period=context.get("current_period") if isinstance(context.get("current_period"), dict) else {},
        last_period=context.get("last_period") if isinstance(context.get("last_period"), dict) else {},
        metrics=[metric.model_dump() for metric in response.metrics],
        hot_styles=[item.model_dump() for item in response.hot_styles],
        suggestions=[item.model_dump() for item in response.suggestions],
        report_summary=response.report_summary,
        generation_mode=response.generation_mode,
    )
    return response.model_copy(update={"snapshot_id": snapshot["snapshot_id"]})


def _report_metrics(period: str, current_period: dict[str, float], last_period: dict[str, float]) -> list[dict[str, str]]:
    try_on_count = int(current_period.get("try_on_count", 0))
    favorite_rate = float(current_period.get("favorite_rate", 0))
    order_rate = float(current_period.get("order_rate", 0))
    boost_order_rate = min(order_rate * 2.2, 0.95)
    boost_try_share = min(max(float(current_period.get("try_rate", 0)) * 1.4, 0.12), 0.85)
    favorite_delta = _delta(favorite_rate, float(last_period.get("favorite_rate", 0)))
    order_delta = _delta(order_rate, float(last_period.get("order_rate", 0)))
    try_delta = _delta(float(current_period.get("try_rate", 0)), float(last_period.get("try_rate", 0)))
    count_delta = _delta(float(try_on_count), float(last_period.get("try_on_count", 0)))
    return [
        _metric("try_on_count", "试戴总次数" if period != "today" else "今日试戴次数", str(try_on_count), count_delta),
        _metric("order_rate", "自然流量下单率", _percent(order_rate), order_delta),
        _metric("boost_order_rate", "投流流量下单率", _percent(boost_order_rate), order_delta),
        _metric("favorite_rate", "试戴收藏率", _percent(favorite_rate), favorite_delta),
        _metric("boost_try_share", "投流试戴占比", _percent(boost_try_share), try_delta),
        _metric("new_styles", "新上架款式", str(max(1, min(6, try_on_count // 5 or 1))), "— 持平"),
    ]


def _hot_style_item(card: PushCardResponse) -> dict[str, object]:
    stats = next((item for item in card.signal_sources if item.signal == "实时行为"), None)
    behavior_value = int(stats.value) if stats else 0
    try_on_count = max(behavior_value // 3, 0)
    favorite_count = max(behavior_value // 8, 0)
    order_count = max(behavior_value // 18, 0)
    favorite_rate = round(favorite_count / try_on_count, 4) if try_on_count else 0
    return {
        "style_id": card.style_id,
        "style_name": card.style_name,
        "hot_score": card.hot_score,
        "life_cycle": card.life_cycle,
        "try_on_count": try_on_count,
        "favorite_count": favorite_count,
        "order_count": order_count,
        "favorite_rate": favorite_rate,
    }


def _period_label(period: str) -> str:
    mapping = {
        "this_week": "本周复盘",
        "this_month": "本月复盘",
        "today": "今日运营日报",
    }
    return mapping.get(period, "运营复盘")


def _metric(key: str, label: str, value: str, delta: str) -> dict[str, str]:
    return {
        "key": key,
        "label": label,
        "value": value,
        "delta": delta,
        "delta_direction": _delta_direction(delta),
    }


def _delta_direction(delta: str) -> str:
    if delta.startswith("+"):
        return "up"
    if delta.startswith("-"):
        return "down"
    return "flat"


def _percent(value: float) -> str:
    return f"{value * 100:.1f}%"


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
