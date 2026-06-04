#!/usr/bin/env python3
"""Discover cross-post trend clusters from cleaned UGC post signals.

This is a bounded-observation trend miner:
- input: cleaned UGC JSON with per-post classification/comment signals
- output: trend pool JSON with clustered trends and supporting posts

It does not assume complete comment coverage. Comment-derived confidence is
discounted through comment_coverage_rate / confidence_penalty when available.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


COMMON_STOPWORDS = {
    "美甲",
    "款式",
    "显白",
    "好看",
    "真的",
    "这个",
    "那个",
    "姐妹",
    "感觉",
    "评论",
    "用户",
    "同款",
    "日常",
    "高级",
    "温柔",
}


@dataclass
class PostSignal:
    post_id: str
    title: str
    image_url: str
    source_url: str
    published_at: str
    like_count: int
    favorite_count: int
    comment_count: int
    trend_weight: float
    confidence_penalty: float
    comment_coverage_rate: float
    clean_status: str
    promotion_type: str
    tags: set[str]
    style_tags: set[str]
    demand_tags: set[str]
    pain_points: set[str]
    purchase_intents: set[str]
    social_proofs: set[str]
    negative_feedbacks: set[str]
    hot_score: float


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover cross-post nail trends from cleaned UGC posts")
    parser.add_argument("--input", required=True, help="Input cleaned UGC JSON path")
    parser.add_argument("--output", required=True, help="Output trend JSON path")
    parser.add_argument("--min-support", type=int, default=2, help="Minimum posts per trend cluster")
    parser.add_argument("--max-trends", type=int, default=20, help="Maximum trends to keep")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    raw = json.loads(input_path.read_text(encoding="utf-8"))
    posts = raw.get("posts")
    if not isinstance(posts, list):
        raise SystemExit("Input JSON must contain a top-level 'posts' array")

    signals = [build_post_signal(post) for post in posts if isinstance(post, dict)]
    candidates = [signal for signal in signals if is_trend_candidate(signal)]
    clusters = cluster_signals(candidates, min_support=args.min_support)
    trends = build_trends(clusters)
    trends.sort(key=lambda item: item["trend_score"], reverse=True)
    trends = trends[: args.max_trends]

    payload = {
        "generated_at": now_iso(),
        "source_post_count": len(posts),
        "candidate_post_count": len(candidates),
        "trend_count": len(trends),
        "trends": trends,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"written: {output_path} source_posts={len(posts)} candidates={len(candidates)} trends={len(trends)}"
    )


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def build_post_signal(post: dict[str, Any]) -> PostSignal:
    comment_insights = post.get("comment_insights") or {}
    raw_tags = normalize_string_list(post.get("raw_tags"))
    style_tags = normalize_string_list(comment_insights.get("style_tags"))
    demand_tags = normalize_string_list(comment_insights.get("user_demands"))
    pain_points = normalize_string_list(comment_insights.get("pain_points"))
    purchase_intents = normalize_string_list(comment_insights.get("purchase_intents"))
    social_proofs = normalize_string_list(comment_insights.get("social_proofs"))
    negative_feedbacks = normalize_string_list(comment_insights.get("negative_feedbacks"))

    fallback_tokens = extract_fallback_tokens(
        " ".join(
            [
                str(post.get("title") or ""),
                str(post.get("content") or ""),
            ]
        )
    )
    tag_set = set(raw_tags) | set(style_tags) | set(fallback_tokens)

    hot_score = compute_post_hot_score(post, comment_insights)
    return PostSignal(
        post_id=str(post.get("post_id") or ""),
        title=str(post.get("title") or ""),
        image_url=first_image(post),
        source_url=str(post.get("source_url") or ""),
        published_at=str(post.get("published_at") or ""),
        like_count=int(post.get("like_count") or 0),
        favorite_count=int(post.get("favorite_count") or 0),
        comment_count=int(post.get("comment_count") or 0),
        trend_weight=clamp_float(post.get("trend_weight"), 1.0),
        confidence_penalty=clamp_float(comment_insights.get("confidence_penalty"), 0.0),
        comment_coverage_rate=clamp_float(comment_insights.get("comment_coverage_rate"), 0.0),
        clean_status=str(post.get("clean_status") or "pending"),
        promotion_type=str(post.get("promotion_type") or "unknown"),
        tags=tag_set,
        style_tags=set(style_tags),
        demand_tags=set(demand_tags),
        pain_points=set(pain_points),
        purchase_intents=set(purchase_intents),
        social_proofs=set(social_proofs),
        negative_feedbacks=set(negative_feedbacks),
        hot_score=hot_score,
    )


def first_image(post: dict[str, Any]) -> str:
    image_urls = post.get("image_urls")
    if isinstance(image_urls, list):
        for item in image_urls:
            text = str(item or "").strip()
            if text:
                return text
    return ""


def clamp_float(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(number) or math.isinf(number):
        return default
    return number


def normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    output: list[str] = []
    for item in value:
        text = normalize_phrase(item)
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def normalize_phrase(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    text = text.strip(" ,.;:!?[](){}\"'`，。；：！？、")
    if not text:
        return ""
    if len(text) == 1:
        return ""
    if text in COMMON_STOPWORDS:
        return ""
    return text


def extract_fallback_tokens(text: str) -> list[str]:
    normalized = re.sub(r"[#/@]", " ", text)
    parts = re.split(r"[\s,，。；;：:！!?？/]+", normalized)
    output: list[str] = []
    for part in parts:
        token = normalize_phrase(part)
        if token and len(token) >= 2 and token not in COMMON_STOPWORDS:
            output.append(token)
    return output[:12]


def compute_post_hot_score(post: dict[str, Any], comment_insights: dict[str, Any]) -> float:
    like_count = int(post.get("like_count") or 0)
    favorite_count = int(post.get("favorite_count") or 0)
    comment_count = int(post.get("comment_count") or 0)
    trend_weight = clamp_float(post.get("trend_weight"), 1.0)
    confidence_penalty = clamp_float(comment_insights.get("confidence_penalty"), 0.0)
    coverage_rate = clamp_float(comment_insights.get("comment_coverage_rate"), 0.0)

    engagement = (
        math.log1p(max(0, like_count)) * 0.35
        + math.log1p(max(0, favorite_count)) * 0.4
        + math.log1p(max(0, comment_count)) * 0.25
    )
    coverage_bonus = 0.85 + min(coverage_rate, 1.0) * 0.15
    penalty_factor = max(0.35, 1.0 - confidence_penalty)
    return round(engagement * trend_weight * coverage_bonus * penalty_factor, 4)


def is_trend_candidate(signal: PostSignal) -> bool:
    if not signal.post_id:
        return False
    if signal.clean_status == "filtered":
        return False
    if not signal.tags:
        return False
    return True


def cluster_signals(signals: list[PostSignal], min_support: int) -> list[list[PostSignal]]:
    pending = sorted(signals, key=lambda item: item.hot_score, reverse=True)
    clusters: list[list[PostSignal]] = []

    while pending:
        seed = pending.pop(0)
        cluster = [seed]
        remaining: list[PostSignal] = []
        seed_keywords = set(top_signal_keywords([seed], limit=6))

        for candidate in pending:
            if should_merge(seed, candidate, seed_keywords):
                cluster.append(candidate)
            else:
                remaining.append(candidate)
        pending = remaining
        if len(cluster) >= min_support:
            clusters.append(cluster)

    return clusters


def should_merge(seed: PostSignal, candidate: PostSignal, seed_keywords: set[str]) -> bool:
    overlap = seed.tags & candidate.tags
    if len(overlap) >= 2:
        return True
    union = seed.tags | candidate.tags
    jaccard = (len(overlap) / len(union)) if union else 0.0
    if jaccard >= 0.28:
        return True
    if seed_keywords and len(seed_keywords & candidate.tags) >= 2:
        return True
    return False


def top_signal_keywords(signals: list[PostSignal], limit: int = 8) -> list[str]:
    counter: Counter[str] = Counter()
    for signal in signals:
        for token in signal.tags:
            counter[token] += 1
        for token in signal.style_tags:
            counter[token] += 2
        for token in signal.purchase_intents:
            counter[token] += 1
        for token in signal.social_proofs:
            counter[token] += 1
    return [item for item, _ in counter.most_common(limit)]


def build_trends(clusters: list[list[PostSignal]]) -> list[dict[str, Any]]:
    trends: list[dict[str, Any]] = []
    for index, cluster in enumerate(clusters, start=1):
        trends.append(build_trend(index, cluster))
    return trends


def build_trend(index: int, cluster: list[PostSignal]) -> dict[str, Any]:
    keywords = top_signal_keywords(cluster, limit=10)
    cluster_sorted = sorted(cluster, key=lambda item: item.hot_score, reverse=True)
    representative = cluster_sorted[0]
    support_count = len(cluster)
    avg_coverage = round(sum(item.comment_coverage_rate for item in cluster) / support_count, 4)
    avg_confidence_penalty = round(sum(item.confidence_penalty for item in cluster) / support_count, 4)
    total_hot_score = sum(item.hot_score for item in cluster)
    trend_score = round(total_hot_score / max(1, support_count) * math.log1p(support_count + 1), 4)
    confidence = round(max(0.2, min(0.98, 1.0 - avg_confidence_penalty * 0.8)), 4)

    life_cycle = infer_life_cycle(cluster)
    demand_counter = Counter(token for item in cluster for token in item.demand_tags)
    pain_counter = Counter(token for item in cluster for token in item.pain_points)
    proof_counter = Counter(token for item in cluster for token in item.social_proofs)
    purchase_counter = Counter(token for item in cluster for token in item.purchase_intents)

    reasoning_parts = [
        f"共有 {support_count} 条支撑帖子，核心关键词为 {', '.join(keywords[:5]) or '暂无'}。",
        f"平均评论覆盖率 {avg_coverage:.2f}，平均置信度惩罚 {avg_confidence_penalty:.2f}。",
    ]
    if demand_counter:
        reasoning_parts.append(f"用户需求集中在 {', '.join(item for item, _ in demand_counter.most_common(3))}。")
    if pain_counter:
        reasoning_parts.append(f"主要痛点包括 {', '.join(item for item, _ in pain_counter.most_common(3))}。")
    if proof_counter:
        reasoning_parts.append(f"评论共识集中在 {', '.join(item for item, _ in proof_counter.most_common(3))}。")

    return {
        "trend_id": f"trend-{index:03d}",
        "core_style": keywords[0] if keywords else representative.title or f"趋势 {index}",
        "representative_image_url": representative.image_url,
        "style_source_image_url": "",
        "supporting_post_ids": [item.post_id for item in cluster_sorted],
        "keywords": keywords,
        "trend_score": trend_score,
        "confidence": confidence,
        "life_cycle": life_cycle,
        "reasoning_summary": " ".join(reasoning_parts),
        "status": recommend_trend_status(trend_score, support_count),
        "push_status": "not_pushed",
        "identified_at": now_iso(),
        "metrics": {
            "support_post_count": support_count,
            "average_comment_coverage_rate": avg_coverage,
            "average_confidence_penalty": avg_confidence_penalty,
            "average_like_count": round(sum(item.like_count for item in cluster) / support_count, 2),
            "average_favorite_count": round(sum(item.favorite_count for item in cluster) / support_count, 2),
            "average_comment_count": round(sum(item.comment_count for item in cluster) / support_count, 2),
            "promotion_post_ratio": round(
                sum(1 for item in cluster if item.promotion_type not in {"unknown", "natural_ugc"}) / support_count,
                4,
            ),
        },
        "comment_signal_summary": {
            "user_demands": [item for item, _ in demand_counter.most_common(8)],
            "pain_points": [item for item, _ in pain_counter.most_common(8)],
            "social_proofs": [item for item, _ in proof_counter.most_common(8)],
            "purchase_intents": [item for item, _ in purchase_counter.most_common(8)],
            "negative_feedbacks": [
                item
                for item, _ in Counter(token for signal in cluster for token in signal.negative_feedbacks).most_common(8)
            ],
        },
        "supporting_posts": [
            {
                "post_id": item.post_id,
                "title": item.title,
                "source_url": item.source_url,
                "published_at": item.published_at,
                "image_url": item.image_url,
                "like_count": item.like_count,
                "favorite_count": item.favorite_count,
                "comment_count": item.comment_count,
                "trend_weight": item.trend_weight,
                "hot_score": item.hot_score,
                "comment_coverage_rate": item.comment_coverage_rate,
                "confidence_penalty": item.confidence_penalty,
            }
            for item in cluster_sorted[:10]
        ],
    }


def infer_life_cycle(cluster: list[PostSignal]) -> str:
    recent_count = 0
    old_count = 0
    for item in cluster:
        dt = parse_datetime(item.published_at)
        if not dt:
            continue
        days = max(0.0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 86400)
        if days <= 14:
            recent_count += 1
        elif days >= 45:
            old_count += 1
    if recent_count >= max(2, len(cluster) // 2):
        return "上升期"
    if old_count >= max(2, len(cluster) // 2):
        return "衰退期"
    if len(cluster) >= 4:
        return "峰值期"
    return "观察期"


def recommend_trend_status(trend_score: float, support_count: int) -> str:
    if trend_score >= 6.5 and support_count >= 3:
        return "promote"
    if trend_score >= 3.5:
        return "watch"
    return "discard"


def parse_datetime(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


if __name__ == "__main__":
    main()
