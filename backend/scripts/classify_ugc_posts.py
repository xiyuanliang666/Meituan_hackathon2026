#!/usr/bin/env python3
"""Classify imported UGC posts for trend cleaning.

Usage:
    cd backend
    python scripts/classify_ugc_posts.py \
      --input mock_data/ugc_posts_from_links.json \
      --output mock_data/ugc_posts_from_links.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.prompts.ugc_classification import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from app.services.multimodal_client import (
    MultimodalModelError,
    generate_text_json_with_gemini,
    generate_text_json_with_qwen,
    is_gemini_enabled,
    is_qwen_vl_enabled,
)


ALLOWED_CATEGORIES = {
    "nail",
    "beauty",
    "fashion",
    "luxury_resale",
    "hygiene",
    "skincare",
    "cosmetics",
    "lifestyle",
    "unknown",
}
ALLOWED_PROMOTION_TYPES = {"natural_ugc", "soft_ad", "hard_ad", "brand_collab", "unknown"}
ALLOWED_CLEAN_STATUSES = {"kept", "kept_with_penalty", "filtered"}
MAX_HISTORICAL_EXAMPLES = 3
CLASSIFICATION_FIELDS = {
    "classification_status",
    "classification_model",
    "classified_at",
    "classification_confidence",
    "is_nail_related",
    "category_guess",
    "is_promotional",
    "promotion_type",
    "promotion_confidence",
    "clean_status",
    "clean_reason",
    "trend_weight",
    "comment_insights",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify UGC posts for trend cleaning")
    parser.add_argument("--input", required=True, help="Input JSON path")
    parser.add_argument("--output", required=True, help="Output JSON path")
    parser.add_argument("--limit", type=int, default=None, help="Only process first N posts")
    parser.add_argument("--force", action="store_true", help="Reclassify posts even if already classified")
    parser.add_argument(
        "--provider",
        choices=("auto", "qwen", "gemini", "mock"),
        default="auto",
        help="LLM provider selection",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    raw = json.loads(input_path.read_text(encoding="utf-8"))
    posts = raw.get("posts")
    if not isinstance(posts, list):
        raise SystemExit("Input JSON must contain a top-level 'posts' array")

    existing_output_posts = load_existing_output_posts(output_path)
    merge_existing_classification(posts, existing_output_posts, force=args.force)
    reference_posts = build_reference_posts(existing_output_posts)

    provider = resolve_provider(args.provider)
    processed = 0
    skipped = 0

    for post in posts:
        if not isinstance(post, dict):
            continue
        ensure_classification_defaults(post)
        if post.get("classification_status") == "done" and not args.force:
            skipped += 1
            continue
        if args.limit is not None and processed >= args.limit:
            break

        result = classify_post(post, provider=provider, reference_posts=reference_posts)
        post.update(result)
        reference_posts.append(post.copy())
        processed += 1
        print(f"[{processed}] {post.get('post_id')} -> {post.get('clean_status')} ({post.get('promotion_type')})")

    output_path.write_text(json.dumps({"posts": posts}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"written: {output_path}")
    print(f"processed={processed} skipped={skipped} provider={provider}")


def load_existing_output_posts(output_path: Path) -> list[dict[str, Any]]:
    if not output_path.exists():
        return []
    try:
        raw = json.loads(output_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    posts = raw.get("posts")
    if not isinstance(posts, list):
        return []
    return [post for post in posts if isinstance(post, dict)]


def merge_existing_classification(
    posts: list[dict[str, Any]],
    existing_posts: list[dict[str, Any]],
    *,
    force: bool,
) -> None:
    if force or not existing_posts:
        return
    existing_by_post_id: dict[str, dict[str, Any]] = {}
    existing_by_source_url: dict[str, dict[str, Any]] = {}
    for post in existing_posts:
        post_id = str(post.get("post_id") or "").strip()
        source_url = str(post.get("source_url") or "").strip()
        if post_id:
            existing_by_post_id[post_id] = post
        if source_url:
            existing_by_source_url[source_url] = post

    for post in posts:
        if not isinstance(post, dict):
            continue
        post_id = str(post.get("post_id") or "").strip()
        source_url = str(post.get("source_url") or "").strip()
        existing = existing_by_post_id.get(post_id) or existing_by_source_url.get(source_url)
        if not existing:
            continue
        for field in CLASSIFICATION_FIELDS:
            if field in existing and field not in post:
                post[field] = existing[field]
            elif field in existing:
                post[field] = existing[field]


def resolve_provider(provider: str) -> str:
    if provider != "auto":
        return provider
    if is_qwen_vl_enabled():
        return "qwen"
    if is_gemini_enabled():
        return "gemini"
    return "mock"


def ensure_classification_defaults(post: dict[str, Any]) -> None:
    post.setdefault("classification_status", "pending")
    post.setdefault("classification_model", "")
    post.setdefault("classified_at", "")
    post.setdefault("classification_confidence", 0.0)
    post.setdefault("is_nail_related", None)
    post.setdefault("category_guess", "unknown")
    post.setdefault("is_promotional", None)
    post.setdefault("promotion_type", "unknown")
    post.setdefault("promotion_confidence", 0.0)
    post.setdefault("clean_status", "pending")
    post.setdefault("clean_reason", "")
    post.setdefault("trend_weight", 1.0)
    post.setdefault(
        "comment_insights",
        {
            "status": "pending",
            "summary": "",
            "risk_flags": [],
            "not_suitable_for": [],
            "failure_cases": [],
            "sentiment": "unknown",
            "positive_signals": [],
        },
    )


def classify_post(
    post: dict[str, Any],
    *,
    provider: str,
    reference_posts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if provider == "mock":
        data = mock_classify(post)
        model_name = "mock"
    else:
        try:
            prompt = build_user_prompt(post, select_historical_examples(post, reference_posts or []))
            if provider == "qwen":
                data = generate_text_json_with_qwen(SYSTEM_PROMPT, prompt)
                model_name = "qwen"
            else:
                data = generate_text_json_with_gemini(SYSTEM_PROMPT, prompt)
                model_name = "gemini"
        except MultimodalModelError:
            data = mock_classify(post)
            model_name = "mock"

    normalized = normalize_classification_result(post, data)
    normalized["classification_status"] = "done"
    normalized["classification_model"] = model_name
    normalized["classified_at"] = now_iso()
    return normalized


def build_user_prompt(post: dict[str, Any], historical_examples: list[dict[str, Any]]) -> str:
    return USER_PROMPT_TEMPLATE.format(
        historical_examples=format_historical_examples(historical_examples),
        source_url=str(post.get("source_url") or ""),
        author_name=str(post.get("author_name") or ""),
        title=str(post.get("title") or ""),
        content=str(post.get("content") or ""),
        raw_tags=", ".join(str(t) for t in (post.get("raw_tags") or [])),
        like_count=int(post.get("like_count") or 0),
        favorite_count=int(post.get("favorite_count") or 0),
        comment_count=int(post.get("comment_count") or 0),
    )


def build_reference_posts(existing_posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    for post in existing_posts:
        if not isinstance(post, dict):
            continue
        if str(post.get("classification_status") or "") != "done":
            continue
        references.append(post.copy())
    return references


def select_historical_examples(post: dict[str, Any], reference_posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    current_post_id = str(post.get("post_id") or "").strip()
    current_source_url = str(post.get("source_url") or "").strip()
    current_tokens = extract_similarity_tokens(post)
    ranked: list[tuple[float, dict[str, Any]]] = []
    for candidate in reference_posts:
        candidate_post_id = str(candidate.get("post_id") or "").strip()
        candidate_source_url = str(candidate.get("source_url") or "").strip()
        if current_post_id and candidate_post_id == current_post_id:
            continue
        if current_source_url and candidate_source_url == current_source_url:
            continue
        candidate_tokens = extract_similarity_tokens(candidate)
        score = similarity_score(current_tokens, candidate_tokens)
        if score <= 0:
            continue
        ranked.append((score, candidate))
    ranked.sort(
        key=lambda item: (
            item[0],
            1 if bool(item[1].get("is_nail_related")) else 0,
            float(item[1].get("classification_confidence") or 0),
        ),
        reverse=True,
    )
    return [candidate for _, candidate in ranked[:MAX_HISTORICAL_EXAMPLES]]


def extract_similarity_tokens(post: dict[str, Any]) -> set[str]:
    parts = [
        str(post.get("title") or ""),
        str(post.get("content") or ""),
        " ".join(str(tag) for tag in (post.get("raw_tags") or [])),
        str(post.get("author_name") or ""),
    ]
    text = " ".join(parts).lower()
    raw_tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9_]+", text)
    return {token for token in raw_tokens if token and token not in {"小红书", "今天", "真的", "这个", "那个"}}


def similarity_score(current_tokens: set[str], candidate_tokens: set[str]) -> float:
    if not current_tokens or not candidate_tokens:
        return 0.0
    overlap = current_tokens & candidate_tokens
    if not overlap:
        return 0.0
    return len(overlap) / max(3, len(current_tokens) ** 0.5)


def format_historical_examples(examples: list[dict[str, Any]]) -> str:
    if not examples:
        return "无。请直接依据帖子内容判断。"
    lines: list[str] = []
    for index, item in enumerate(examples, start=1):
        lines.append(
            "\n".join(
                [
                    f"样本{index}:",
                    f"- 标题: {str(item.get('title') or '')}",
                    f"- 标签: {', '.join(str(tag) for tag in (item.get('raw_tags') or []))}",
                    f"- 分类结果: is_nail_related={bool(item.get('is_nail_related'))}, category_guess={str(item.get('category_guess') or 'unknown')}, is_promotional={bool(item.get('is_promotional'))}, promotion_type={str(item.get('promotion_type') or 'unknown')}, clean_status={str(item.get('clean_status') or 'pending')}, trend_weight={item.get('trend_weight')}",
                    f"- 原因: {str(item.get('clean_reason') or '')}",
                ]
            )
        )
    return "\n\n".join(lines)


def normalize_classification_result(post: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    is_nail_related = bool(data.get("is_nail_related"))
    category_guess = str(data.get("category_guess") or "unknown").strip().lower()
    if category_guess not in ALLOWED_CATEGORIES:
        category_guess = "unknown"

    is_promotional = bool(data.get("is_promotional"))
    promotion_type = str(data.get("promotion_type") or "unknown").strip().lower()
    if promotion_type not in ALLOWED_PROMOTION_TYPES:
        promotion_type = "unknown"

    clean_reason = str(data.get("clean_reason") or "").strip()
    classification_confidence = clamp_float(data.get("classification_confidence"), default=0.65)
    promotion_confidence = clamp_float(data.get("promotion_confidence"), default=0.5)
    requested_clean_status = str(data.get("clean_status") or "").strip().lower()
    requested_weight = clamp_float(data.get("trend_weight"), default=1.0)

    if not is_nail_related:
        clean_status = "filtered"
        trend_weight = 0.0
        if not clean_reason:
            clean_reason = "内容主题与美甲趋势分析无关"
    elif is_promotional:
        clean_status = "kept_with_penalty"
        trend_weight = min(requested_weight, default_weight_for_promotion(promotion_type))
        trend_weight = min(trend_weight, 0.8)
        if not clean_reason:
            clean_reason = "内容与美甲相关，但带有推广属性，趋势分析时应降权"
    else:
        clean_status = "kept"
        trend_weight = max(requested_weight, 0.9)
        if not clean_reason:
            clean_reason = "内容与美甲相关，且更接近自然用户分享"

    if requested_clean_status in ALLOWED_CLEAN_STATUSES and clean_status == "kept":
        clean_status = requested_clean_status

    return {
        "is_nail_related": is_nail_related,
        "category_guess": category_guess,
        "is_promotional": is_promotional,
        "promotion_type": promotion_type,
        "clean_status": clean_status,
        "clean_reason": clean_reason,
        "trend_weight": round(max(0.0, min(1.0, trend_weight)), 4),
        "classification_confidence": classification_confidence,
        "promotion_confidence": promotion_confidence,
    }


def default_weight_for_promotion(promotion_type: str) -> float:
    if promotion_type == "hard_ad":
        return 0.4
    if promotion_type == "brand_collab":
        return 0.6
    if promotion_type == "soft_ad":
        return 0.7
    return 0.65


def clamp_float(value: Any, default: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = default
    return max(0.0, min(1.0, numeric))


def mock_classify(post: dict[str, Any]) -> dict[str, Any]:
    haystack = " ".join(
        [
            str(post.get("title") or ""),
            str(post.get("content") or ""),
            " ".join(str(tag) for tag in (post.get("raw_tags") or [])),
        ]
    ).lower()

    nail_keywords = ("美甲", "甲片", "猫眼", "法式", "晕染", "穿戴甲", "指甲", "甲油", "腮红甲")
    promotion_keywords = ("合作", "团购", "门店", "预约", "打卡", "到店", "商单", "广告", "推广")
    non_nail_keywords = ("回收", "包包", "奢侈品", "腕表", "卫生巾", "护肤", "粉底", "香水")

    is_nail_related = any(keyword in haystack for keyword in nail_keywords) and not any(
        keyword in haystack for keyword in non_nail_keywords
    )
    is_promotional = any(keyword in haystack for keyword in promotion_keywords)

    if not is_nail_related:
        return {
            "is_nail_related": False,
            "category_guess": "unknown",
            "is_promotional": is_promotional,
            "promotion_type": "soft_ad" if is_promotional else "unknown",
            "clean_status": "filtered",
            "clean_reason": "文本信号显示与美甲主题无关",
            "trend_weight": 0.0,
            "classification_confidence": 0.55,
            "promotion_confidence": 0.55 if is_promotional else 0.3,
        }

    if is_promotional:
        return {
            "is_nail_related": True,
            "category_guess": "nail",
            "is_promotional": True,
            "promotion_type": "soft_ad",
            "clean_status": "kept_with_penalty",
            "clean_reason": "内容与美甲相关，但存在推广导流口吻",
            "trend_weight": 0.7,
            "classification_confidence": 0.65,
            "promotion_confidence": 0.65,
        }

    return {
        "is_nail_related": True,
        "category_guess": "nail",
        "is_promotional": False,
        "promotion_type": "natural_ugc",
        "clean_status": "kept",
        "clean_reason": "内容与美甲趋势相关，更接近自然UGC",
        "trend_weight": 1.0,
        "classification_confidence": 0.6,
        "promotion_confidence": 0.2,
    }


def now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


if __name__ == "__main__":
    main()
