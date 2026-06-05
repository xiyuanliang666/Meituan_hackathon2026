from __future__ import annotations

from typing import Any

from app.data.nail_taxonomy_v2_seed import ARRAY_FIELD_KEYS
from app.services.business_db import (
    create_merchant_trend_action,
    create_style,
    get_style_by_source_trend_id,
    get_trend,
)
from app.services.taxonomy_store import get_approved_values_map


def build_style_tags_from_trend(trend: dict[str, Any]) -> dict[str, list[str]]:
    approved = get_approved_values_map()
    comment_signal_summary = trend.get("comment_signal_summary") or {}
    metrics = trend.get("metrics") or {}
    candidate_values: list[str] = []

    keywords = trend.get("keywords") or []
    if isinstance(keywords, list):
        candidate_values.extend(str(item).strip() for item in keywords if str(item).strip())

    for key in ("style_tags", "user_demands", "pain_points", "social_proofs", "purchase_intents", "negative_feedbacks"):
        values = comment_signal_summary.get(key) or []
        if isinstance(values, list):
            candidate_values.extend(str(item).strip() for item in values if str(item).strip())

    core_style_tags = metrics.get("core_style_tags") or []
    if isinstance(core_style_tags, list):
        candidate_values.extend(str(item).strip() for item in core_style_tags if str(item).strip())

    deduped_candidates: list[str] = []
    seen: set[str] = set()
    for value in candidate_values:
        if not value or value in seen:
            continue
        seen.add(value)
        deduped_candidates.append(value)

    tags: dict[str, list[str]] = {field_key: [] for field_key in ARRAY_FIELD_KEYS}
    matched: set[str] = set()
    for field_key in ARRAY_FIELD_KEYS:
        allowed = approved.get(field_key, set())
        values = [value for value in deduped_candidates if value in allowed]
        if values:
            tags[field_key] = values
            matched.update(values)

    unmatched = [value for value in deduped_candidates if value not in matched]
    if unmatched:
        tags["candidate_tags"] = unmatched
    return tags


def convert_trend_to_draft(
    *,
    trend_id: str,
    merchant_id: str,
    style_name: str | None = None,
    use_trend_tags: bool = True,
    note: str = "",
) -> dict[str, Any]:
    trend = get_trend(trend_id)
    if not trend:
        raise ValueError("trend not found")

    existing = get_style_by_source_trend_id(trend_id)
    if existing:
        return {
            "trend_id": trend_id,
            "style_id": existing["style_id"],
            "style_name": existing.get("style_name") or trend.get("core_style") or "趋势草稿",
            "image_url": existing.get("enhanced_style_image_url", ""),
            "status": existing.get("status", "draft"),
            "review_status": existing.get("review_status", "draft_pending_asset"),
            "material_status": existing.get("material_status", "style_image_missing"),
            "source": existing.get("source", "trend_agent"),
            "source_trend_id": existing.get("source_trend_id") or trend_id,
            "tags": existing.get("tags", {}),
            "existing": True,
        }

    # Fix 6: UGC representative images (typically XHS screenshots) are NOT
    # suitable as product images. Only use style_source_image_url if present.
    image_url = (trend.get("style_source_image_url") or "").strip()
    if not image_url:
        # Fall back to the representative but flag as missing product image
        image_url = (trend.get("representative_image_url") or "").strip()

    # Fix 6: material_status reflects whether we have a proper product image
    material_status = "ready" if (trend.get("style_source_image_url") or "").strip() else "style_image_missing"

    tags = build_style_tags_from_trend(trend) if use_trend_tags else {}
    final_style_name = (style_name or "").strip() or str(trend.get("core_style") or "趋势草稿")

    created = create_style(
        style_name=final_style_name,
        image_url=image_url,
        tags=tags,
        status="draft",
        # Fix 6: draft_pending_asset — trends don't have proper product images,
        # the merchant needs to replace with a real product shot before publishing.
        review_status="draft_pending_asset",
        source="trend_agent",
        material_status=material_status,
        source_trend_id=trend_id,
    )

    create_merchant_trend_action(
        merchant_id=merchant_id.strip(),
        trend_id=trend_id,
        action="converted_to_draft",
        note=note.strip(),
        draft_style_id=created["style_id"],
    )

    return {
        "trend_id": trend_id,
        "style_id": created["style_id"],
        "style_name": created["style_name"],
        "image_url": created["image_url"],
        "status": created["status"],
        "review_status": created["review_status"],
        "material_status": created.get("material_status", material_status),
        "source": created.get("source", "trend_agent"),
        "source_trend_id": created.get("source_trend_id") or trend_id,
        "tags": created.get("tags", {}),
        "existing": False,
    }
