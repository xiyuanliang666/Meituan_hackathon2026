"""UGC Trend Discovery Agent — core clustering, scoring, lifecycle, and taxonomy evolution."""
from __future__ import annotations

import difflib
import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
UTC = timezone.utc
from typing import Any


# ---------------------------------------------------------------------------
# Stopwords & taxonomy field keys (must match taxonomy_store.py)
# ---------------------------------------------------------------------------
COMMON_STOPWORDS = {
    "美甲", "款式", "显白", "好看", "真的", "这个", "那个",
    "姐妹", "感觉", "评论", "用户", "同款", "日常", "高级", "温柔",
}

# taxonomy dimensions used for canonical trend keys and clustering
TAXONOMY_CLUSTER_FIELDS = (
    "nail_technique", "color_system", "style_tags", "nail_shape",
    "nail_length", "scene_tags", "season_tags",
)

# ---------------------------------------------------------------------------
# PostSignal
# ---------------------------------------------------------------------------
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
    # raw free-text tags from source
    raw_tags: set[str] = field(default_factory=set)
    # taxonomy-normalized tags  {field_key: {values}}
    normalized_tags: dict[str, set[str]] = field(default_factory=dict)
    # comment-derived signals
    style_tags: set[str] = field(default_factory=set)
    demand_tags: set[str] = field(default_factory=set)
    pain_points: set[str] = field(default_factory=set)
    purchase_intents: set[str] = field(default_factory=set)
    social_proofs: set[str] = field(default_factory=set)
    negative_feedbacks: set[str] = field(default_factory=set)
    snapshots: list[dict[str, Any]] = field(default_factory=list)
    # computed
    hot_score: float = 0.0
    signal_quality: str = "active"
    unmatched_raw_tags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Candidate taxonomy term (represents a potential new official tag)
# ---------------------------------------------------------------------------
@dataclass
class CandidateTaxonomyTerm:
    candidate_term: str
    normalized_form: str
    target_field: str
    frequency: int
    variant_forms: list[str]
    related_official_tags: list[str]
    support_post_ids: list[str]
    growth_rate_7d: float = 0.0
    discovered_run_id: str = ""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def discover_trends_from_posts(
    posts: list[dict[str, Any]],
    min_support: int = 2,
    max_trends: int = 20,
    taxonomy_store: Any = None,           # optional taxonomy_store module
    candidate_pool: list[CandidateTaxonomyTerm] | None = None,
) -> dict[str, Any]:
    """Main entry point — returns {trends, candidates, health}."""
    signals = [build_post_signal(post, taxonomy_store) for post in posts if isinstance(post, dict)]

    # ---------- Fix 8: signal quality filter ----------
    active = [s for s in signals if s.signal_quality == "active"]
    cold = [s for s in signals if s.signal_quality == "cold_start"]
    low_content = [s for s in signals if s.signal_quality == "low_content"]
    discarded = [s for s in signals if s.signal_quality == "discarded_low_signal"]
    clustering_pool = active + [apply_quality_penalty(s, 0.5) for s in cold] + \
                      [apply_quality_penalty(s, 0.75) for s in low_content]

    # ---------- Fix 3: pairwise graph connected components ----------
    candidates = [s for s in clustering_pool if is_trend_candidate(s)]
    clusters = graph_cluster_signals(candidates, min_support=min_support)
    trends = build_trends(clusters)

    # ---------- Fix 5: aggregate candidate taxonomy terms ----------
    discovered_candidates: list[dict[str, Any]] = []
    if taxonomy_store is not None and candidate_pool is not None:
        discovered_candidates = aggregate_candidate_terms(
            signals, taxonomy_store, min_frequency=3,
        )
        candidate_pool.extend([
            CandidateTaxonomyTerm(**dc) for dc in discovered_candidates
        ])

    trends.sort(key=lambda item: item["trend_score"], reverse=True)
    trends = trends[:max_trends]

    return {
        "generated_at": now_iso(),
        "source_post_count": len(posts),
        "candidate_post_count": len(candidates),
        "trend_count": len(trends),
        "trends": trends,
        "signal_quality_summary": {
            "active": len(active),
            "cold_start": len(cold),
            "low_content": len(low_content),
            "discarded_low_signal": len(discarded),
        },
        "candidate_taxonomy_terms": discovered_candidates,
    }


# ---------------------------------------------------------------------------
# Fix 5 + Fix 8: build_post_signal with taxonomy normalization
# ---------------------------------------------------------------------------
def build_post_signal(post: dict[str, Any], taxonomy_store: Any = None) -> PostSignal:
    comment_insights = post.get("comment_insights") or {}
    raw_tags_list = normalize_string_list(post.get("raw_tags"))
    style_tags_list = normalize_string_list(comment_insights.get("style_tags"))
    demand_tags_list = normalize_string_list(comment_insights.get("user_demands"))
    pain_points_list = normalize_string_list(comment_insights.get("pain_points"))
    purchase_intents_list = normalize_string_list(comment_insights.get("purchase_intents"))
    social_proofs_list = normalize_string_list(comment_insights.get("social_proofs"))
    negative_list = normalize_string_list(comment_insights.get("negative_feedbacks"))
    hot_score = compute_post_hot_score(post)

    # ---------- taxonomy normalization ----------
    raw_set = set(raw_tags_list)
    normalized: dict[str, set[str]] = {}
    unmatched: list[str] = []
    if taxonomy_store is not None:
        normalized, unmatched = normalize_raw_tags(raw_set, taxonomy_store)
    else:
        # fallback: put all tags into a generic bucket
        for tag in raw_set:
            normalized.setdefault("style_tags", set()).add(tag)

    signal = PostSignal(
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
        raw_tags=raw_set,
        normalized_tags=normalized,
        style_tags=set(style_tags_list),
        demand_tags=set(demand_tags_list),
        pain_points=set(pain_points_list),
        purchase_intents=set(purchase_intents_list),
        social_proofs=set(social_proofs_list),
        negative_feedbacks=set(negative_list),
        snapshots=normalize_snapshots(post.get("snapshots")),
        hot_score=hot_score,
        unmatched_raw_tags=unmatched,
    )

    # ---------- Fix 8: assess signal quality ----------
    signal.signal_quality = assess_signal_quality(signal)

    return signal


# ---------------------------------------------------------------------------
# Fix 5: normalize raw XHS tags to official taxonomy
# ---------------------------------------------------------------------------
def normalize_raw_tags(
    raw_tags: set[str],
    taxonomy_store: Any,
) -> tuple[dict[str, set[str]], list[str]]:
    """Map free-form tags to taxonomy dimensions. Returns (normalized, unmatched)."""
    approved = taxonomy_store.get_approved_values_map()
    all_values: dict[str, set[str]] = {}
    for field_key in TAXONOMY_CLUSTER_FIELDS:
        all_values[field_key] = approved.get(field_key, set())

    normalized: dict[str, set[str]] = {}
    unmatched: list[str] = []

    for raw in raw_tags:
        cleaned = normalize_phrase(raw)
        if not cleaned:
            continue

        matched = False
        candidates = [cleaned]
        if cleaned.endswith("美甲") and len(cleaned) > 2:
            trimmed = cleaned[:-2].strip()
            if trimmed:
                candidates.append(trimmed)

        # exact match against approved values, with a light suffix normalization
        for field_key, approved_set in all_values.items():
            matched_value = next((candidate for candidate in candidates if candidate in approved_set), "")
            if matched_value:
                normalized.setdefault(field_key, set()).add(matched_value)
                matched = True
                break
        if not matched:
            unmatched.append(cleaned)

    return normalized, unmatched


def _merge_into_normalized(
    normalized: dict[str, set[str]],
    tag: str,
    taxonomy_store: Any,
) -> None:
    """Try to assign a comment-derived style tag to a taxonomy field."""
    if taxonomy_store is None:
        normalized.setdefault("style_tags", set()).add(tag)
        return
    approved = taxonomy_store.get_approved_values_map()
    for field_key in TAXONOMY_CLUSTER_FIELDS:
        if tag in approved.get(field_key, set()):
            normalized.setdefault(field_key, set()).add(tag)
            return
    normalized.setdefault("style_tags", set()).add(tag)


# ---------------------------------------------------------------------------
# Fix 8: signal quality assessment
# ---------------------------------------------------------------------------
def assess_signal_quality(signal: PostSignal) -> str:
    has_engagement = (
        signal.like_count > 0
        or signal.favorite_count > 0
        or signal.comment_count > 0
    )
    has_content = bool(signal.normalized_tags) or bool(signal.title)
    if not has_engagement and not has_content:
        return "discarded_low_signal"
    if not has_engagement and has_content:
        return "cold_start"
    if has_engagement and not has_content:
        return "low_content"
    return "active"


def apply_quality_penalty(signal: PostSignal, factor: float) -> PostSignal:
    signal.hot_score = round(signal.hot_score * factor, 4)
    return signal


# ---------------------------------------------------------------------------
# Fix 5: aggregate candidate taxonomy terms
# ---------------------------------------------------------------------------
def aggregate_candidate_terms(
    signals: list[PostSignal],
    taxonomy_store: Any,
    min_frequency: int = 3,
) -> list[dict[str, Any]]:
    """Discover high-frequency unmapped terms and suggest new taxonomy entries."""
    # Count raw unmatched tags
    counter: Counter[str] = Counter()
    tag_posts: dict[str, list[str]] = {}
    for signal in signals:
        for tag in signal.unmatched_raw_tags:
            counter[tag] += 1
            tag_posts.setdefault(tag, []).append(signal.post_id)

    # Group similar variants  → normalized form
    groups = _group_variant_tags(
        [(tag, count) for tag, count in counter.most_common()],
        tag_posts,
        signals,
        min_frequency,
    )

    return [
        {
            "candidate_term": g["normalized_form"],
            "normalized_form": g["normalized_form"],
            "target_field": g["target_field"],
            "frequency": g["frequency"],
            "variant_forms": g["variants"],
            "related_official_tags": g["related_official"],
            "support_post_ids": g["support_post_ids"],
            "growth_rate_7d": g.get("growth_rate_7d", 0.0),
        }
        for g in groups
    ]


def _group_variant_tags(
    counted: list[tuple[str, int]],
    tag_posts: dict[str, list[str]],
    signals: list[PostSignal],
    min_frequency: int,
) -> list[dict[str, Any]]:
    """Group variant forms using edit-distance similarity.

    Uses difflib.SequenceMatcher for Chinese text — handles insertion/deletion/
    substitution variants (e.g. "奶呼呼" ↔ "奶芙芙") far better than character-set
    overlap. The swap-in point for embedding cosine similarity is the
    ``_tag_similarity`` function below.
    """
    groups: list[dict[str, Any]] = []
    used: set[str] = set()

    for tag, count in counted:
        if tag in used or count < min_frequency:
            continue
        variants = [tag]
        total_freq = count
        post_ids = list(tag_posts.get(tag, []))
        for other, other_count in counted:
            if other in used or other == tag:
                continue
            # Fast pre-filter: skip pairs with no common bigram
            if not _share_bigram(tag, other):
                continue
            if _tag_similarity(tag, other) >= 0.55:
                variants.append(other)
                total_freq += other_count
                post_ids.extend(tag_posts.get(other, []))
                used.add(other)
        used.add(tag)

        target_field = _infer_target_field(tag, signals)

        groups.append({
            "normalized_form": _pick_canonical_form(variants),
            "target_field": target_field,
            "frequency": total_freq,
            "variants": sorted(set(variants)),
            "related_official": _related_official_tags(post_ids, signals),
            "support_post_ids": sorted(set(post_ids))[:20],
            "growth_rate_7d": 0.0,
        })

    return groups


def _tag_similarity(a: str, b: str) -> float:
    """Edit-distance similarity via difflib.SequenceMatcher.

    Returns a value in [0, 1].  Good for Chinese because it captures:
    - prefix/suffix variants:  "奶呼呼" vs "奶呼呼美甲"  → high
    - character substitutions: "奶呼呼" vs "奶芙芙"    → moderate
    - completely unrelated:   "奶呼呼" vs "镜面光"    → low

    Swap-in point for embedding cosine similarity.
    """
    return difflib.SequenceMatcher(None, a, b).ratio()


def _share_bigram(a: str, b: str) -> bool:
    """Fast pre-filter: check if two strings share at least one character bigram."""
    if len(a) < 2 or len(b) < 2:
        return True  # short strings: skip pre-filter, let _tag_similarity decide
    bigrams_a = {a[i:i + 2] for i in range(len(a) - 1)}
    bigrams_b = {b[i:i + 2] for i in range(len(b) - 1)}
    return not bigrams_a.isdisjoint(bigrams_b)


def _pick_canonical_form(variants: list[str]) -> str:
    """Pick the best representative form from a group of variants.

    Prefers the longest form that isn't excessively long (avoids picking
    a full-sentence raw tag as the canonical name).
    """
    if not variants:
        return ""
    # Sort by length descending, but cap at 12 chars
    scored = sorted(variants, key=lambda v: (min(len(v), 12), -len(v)), reverse=True)
    return scored[0]


def _infer_target_field(tag: str, signals: list[PostSignal]) -> str:
    """Infer which taxonomy dimension the tag belongs to by looking at
    co-occurring official tags in the same posts."""
    field_hits: Counter[str] = Counter()
    for signal in signals:
        if tag in signal.unmatched_raw_tags:
            for field_key in signal.normalized_tags:
                field_hits[field_key] += 1
    if field_hits:
        return field_hits.most_common(1)[0][0]
    return "style_tags"  # default


def _related_official_tags(
    post_ids: list[str],
    signals: list[PostSignal],
) -> list[str]:
    """Collect official tags that co-occur with the candidate across posts."""
    sig_map = {s.post_id: s for s in signals}
    counter: Counter[str] = Counter()
    for pid in post_ids:
        sig = sig_map.get(pid)
        if sig is None:
            continue
        for vals in sig.normalized_tags.values():
            for v in vals:
                counter[v] += 1
    return [item for item, _ in counter.most_common(8)]


# ---------------------------------------------------------------------------
# Fix 3: graph-based clustering (pairwise adjacency → connected components)
# ---------------------------------------------------------------------------
def graph_cluster_signals(
    signals: list[PostSignal],
    min_support: int,
) -> list[list[PostSignal]]:
    n = len(signals)
    if n == 0:
        return []

    # build adjacency
    adj: list[set[int]] = [set() for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            if should_merge(signals[i], signals[j]):
                adj[i].add(j)
                adj[j].add(i)

    # connected components via DFS
    visited: set[int] = set()
    clusters: list[list[PostSignal]] = []
    for i in range(n):
        if i in visited:
            continue
        comp: list[int] = []
        stack = [i]
        while stack:
            v = stack.pop()
            if v in visited:
                continue
            visited.add(v)
            comp.append(v)
            stack.extend(adj[v] - visited)
        if len(comp) >= min_support:
            clusters.append([signals[idx] for idx in comp])

    return refine_clusters_by_primary_technique(clusters, min_support)


def refine_clusters_by_primary_technique(
    clusters: list[list[PostSignal]],
    min_support: int,
) -> list[list[PostSignal]]:
    refined: list[list[PostSignal]] = []
    for cluster in clusters:
        technique_buckets: dict[str, list[PostSignal]] = {}
        for item in cluster:
            techniques = sorted(item.normalized_tags.get("nail_technique", set()))
            if not techniques:
                continue
            technique_buckets.setdefault(techniques[0], []).append(item)

        valid_buckets = [bucket for bucket in technique_buckets.values() if len(bucket) >= min_support]
        if not valid_buckets:
            refined.append(cluster)
            continue

        covered_ids = {item.post_id for bucket in valid_buckets for item in bucket}
        for bucket in valid_buckets:
            refined.append(bucket)

        residual = [item for item in cluster if item.post_id not in covered_ids]
        if len(residual) >= min_support:
            refined.append(residual)

    return refined


# ---------------------------------------------------------------------------
# Fix 3: pairwise merge decision with hard taxonomy constraints
# ---------------------------------------------------------------------------
def should_merge(a: PostSignal, b: PostSignal) -> bool:
    # --- soft: tag overlap (raw tags for broad recall) ---
    raw_overlap = a.raw_tags & b.raw_tags
    raw_union = a.raw_tags | b.raw_tags
    raw_jaccard = (len(raw_overlap) / len(raw_union)) if raw_union else 0.0

    # --- soft: normalized tag overlap ---
    norm_tags_a = set().union(*a.normalized_tags.values()) if a.normalized_tags else set()
    norm_tags_b = set().union(*b.normalized_tags.values()) if b.normalized_tags else set()
    norm_overlap = norm_tags_a & norm_tags_b
    technique_overlap = a.normalized_tags.get("nail_technique", set()) & b.normalized_tags.get("nail_technique", set())

    # --- hard constraint: at least 1 shared core style tag AND ≥2 dimension hits ---
    core_fields = {"nail_technique", "color_system", "nail_length"}
    core_hit = any(
        bool(
            a.normalized_tags.get(f, set()) &
            (b.normalized_tags.get(f, set()))
        )
        for f in core_fields
    )
    dim_hits = sum(
        1
        for f in TAXONOMY_CLUSTER_FIELDS
        if bool(
            a.normalized_tags.get(f, set()) &
            (b.normalized_tags.get(f, set()))
        )
    )

    alias_technique_hit = any(
        token and (
            f"{token}美甲" in a.raw_tags
            or f"{token}美甲" in b.raw_tags
        )
        for token in technique_overlap
    )

    # Shared canonical nail technique plus explicit alias evidence is enough to
    # keep close variants together, e.g. 猫眼 and 猫眼美甲 after normalization.
    if technique_overlap and (alias_technique_hit or raw_jaccard >= 0.12 or dim_hits >= 2):
        return True
    if core_hit and dim_hits >= 2:
        return True
    if raw_jaccard >= 0.28 and len(norm_overlap) >= 2:
        return True
    return False


# ---------------------------------------------------------------------------
# Fix 7: canonical trend key generation
# ---------------------------------------------------------------------------
def canonical_trend_key(normalized_tags: dict[str, set[str]]) -> str:
    parts = []
    for field in TAXONOMY_CLUSTER_FIELDS:
        vals = sorted(normalized_tags.get(field, set()))
        if vals:
            parts.append(f"{field}:{'|'.join(vals)}")
    raw = ";".join(parts)
    if not raw:
        return "trend_unknown"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"trend_{digest}"


# ---------------------------------------------------------------------------
# Fix 4: data_lifecycle + trend_lifecycle
# ---------------------------------------------------------------------------
def compute_lifecycles(
    cluster: list[PostSignal],
    previous_score_history: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    """Return {data_lifecycle, trend_lifecycle}."""
    # --- data_lifecycle: based on post timestamps ---
    now = datetime.now(UTC)
    recent = old = 0
    for item in cluster:
        dt = parse_datetime(item.published_at)
        if not dt:
            continue
        days = (now - dt.astimezone(UTC)).total_seconds() / 86400
        if days <= 14:
            recent += 1
        elif days >= 45:
            old += 1
    if recent >= max(2, len(cluster) // 2):
        data_lifecycle = "recent"
    elif old >= max(2, len(cluster) // 2):
        data_lifecycle = "long_tail"
    else:
        # check if the oldest post falls in the mid-term range (14-45 days)
        timestamps = sorted(
            t for item in cluster
            if (t := parse_datetime(item.published_at))
        )
        if timestamps:
            oldest_days = (now - timestamps[0].astimezone(UTC)).total_seconds() / 86400
            newest_days = (now - timestamps[-1].astimezone(UTC)).total_seconds() / 86400
            if oldest_days > 14 and newest_days <= 45:
                data_lifecycle = "mid_term"
            else:
                data_lifecycle = "recent"
        else:
            data_lifecycle = "recent"

    # --- trend_lifecycle: requires score history ---
    if not previous_score_history or len(previous_score_history) < 2:
        trend_lifecycle = "insufficient_history"
    else:
        scores = [entry.get("score", 0) for entry in previous_score_history[-3:]]
        if len(scores) >= 2 and all(scores[i] < scores[i + 1] for i in range(len(scores) - 1)):
            trend_lifecycle = "rising"
        elif len(scores) >= 2 and all(scores[i] > scores[i + 1] for i in range(len(scores) - 1)):
            trend_lifecycle = "declining"
        elif scores:
            avg_score = sum(scores) / len(scores)
            trend_lifecycle = "stable" if avg_score >= 5 else "declining"
        else:
            trend_lifecycle = "insufficient_history"

    return {"data_lifecycle": data_lifecycle, "trend_lifecycle": trend_lifecycle}


def infer_display_lifecycle(
    data_lifecycle: str,
    trend_lifecycle: str,
) -> str:
    """Map the two lifecycle fields to a display-friendly label for frontend."""
    if trend_lifecycle == "rising":
        return "上升期"
    if trend_lifecycle == "declining":
        return "衰退期"
    if trend_lifecycle == "stable":
        return "峰值期"
    return "观察期"


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
def compute_post_hot_score(
    post: dict[str, Any],
) -> float:
    like_count = int(post.get("like_count") or 0)
    favorite_count = int(post.get("favorite_count") or 0)
    comment_count = int(post.get("comment_count") or 0)
    trend_weight = clamp_float(post.get("trend_weight"), 1.0)
    engagement = (
        math.log1p(max(0, like_count)) * 0.35
        + math.log1p(max(0, favorite_count)) * 0.4
        + math.log1p(max(0, comment_count)) * 0.25
    )
    return round(engagement * trend_weight, 4)


# ---------------------------------------------------------------------------
# Trend building
# ---------------------------------------------------------------------------
def build_trends(clusters: list[list[PostSignal]]) -> list[dict[str, Any]]:
    return [build_trend(index, cluster) for index, cluster in enumerate(clusters, start=1)]


def build_trend(index: int, cluster: list[PostSignal]) -> dict[str, Any]:
    keywords = top_signal_keywords(cluster, limit=10)
    cluster_sorted = sorted(cluster, key=lambda item: item.hot_score, reverse=True)
    representative = cluster_sorted[0]
    support_count = len(cluster)
    avg_coverage = round(
        sum(item.comment_coverage_rate for item in cluster) / support_count, 4,
    )
    avg_confidence_penalty = round(
        sum(item.confidence_penalty for item in cluster) / support_count, 4,
    )
    total_hot_score = sum(item.hot_score for item in cluster)
    velocity_metrics = compute_velocity_metrics(cluster)
    trend_score = round(
        total_hot_score / max(1, support_count) * math.log1p(support_count + 1), 4,
    )
    confidence = round(
        max(0.2, min(0.98, 1.0 - avg_confidence_penalty * 0.8)), 4,
    )

    # aggregated by taxonomy dimension
    merged_tags: dict[str, Counter[str]] = {}
    for item in cluster:
        for field in TAXONOMY_CLUSTER_FIELDS:
            for val in item.normalized_tags.get(field, set()):
                merged_tags.setdefault(field, Counter())[val] += 1

    lifecycles = compute_lifecycles(cluster)
    display_lifecycle = infer_display_lifecycle(
        lifecycles["data_lifecycle"], lifecycles["trend_lifecycle"],
    )

    style_counter = Counter(
        token
        for item in cluster
        for token in item.normalized_tags.get("style_tags", set())
    )
    technique_counter = Counter(
        token
        for item in cluster
        for token in item.normalized_tags.get("nail_technique", set())
    )
    demand_counter = Counter(token for item in cluster for token in item.demand_tags)
    pain_counter = Counter(token for item in cluster for token in item.pain_points)
    proof_counter = Counter(token for item in cluster for token in item.social_proofs)
    purchase_counter = Counter(token for item in cluster for token in item.purchase_intents)
    negative_counter = Counter(token for item in cluster for token in item.negative_feedbacks)

    support_score = round(math.log1p(support_count + 1), 4)
    engagement_score = round(total_hot_score / max(1, support_count), 4)
    comment_signal_score = round(
        len(demand_counter) * 0.3
        + len(purchase_counter) * 0.25
        + len(proof_counter) * 0.2
        + len(style_counter) * 0.15
        - len(negative_counter) * 0.1,
        4,
    )
    coverage_confidence_score = round(
        max(0.0, 1.0 - avg_confidence_penalty) * max(0.2, avg_coverage), 4,
    )

    reasoning_parts = [
        f"共有 {support_count} 条支撑帖子，核心关键词为 {', '.join(keywords[:5]) or '暂无'}。",
        f"趋势热度分 {trend_score:.2f}，增长速度分 {velocity_metrics['velocity_score']:.2f}。",
        f"平均评论覆盖率 {avg_coverage:.2f}，平均置信度惩罚 {avg_confidence_penalty:.2f}。",
    ]
    if style_counter:
        reasoning_parts.append(
            f"核心风格标签集中在 {', '.join(item for item, _ in style_counter.most_common(3))}。",
        )
    if demand_counter:
        reasoning_parts.append(
            f"用户需求集中在 {', '.join(item for item, _ in demand_counter.most_common(3))}。",
        )
    if velocity_metrics["velocity_score"] >= 3:
        reasoning_parts.append(
            f"最近窗口互动增幅约 {velocity_metrics['recent_growth_ratio']:.2f}，近 14 天新帖占比 {velocity_metrics['recent_post_ratio']:.2f}。",
        )

    # ------ Fix 7: canonical trend_id ------
    canonical_id = canonical_trend_key(merged_tags)

    # ------ Fix 8: signal quality distribution ------
    quality_dist: dict[str, int] = {}
    for item in cluster:
        quality_dist[item.signal_quality] = quality_dist.get(item.signal_quality, 0) + 1

    preferred_core_style = (
        top_counter_items(technique_counter, limit=1)[0]
        if technique_counter else top_counter_items(style_counter, limit=1)[0]
        if style_counter else keywords[0]
        if keywords else representative.title or f"趋势 {canonical_id[:8]}"
    )

    return {
        "trend_id": canonical_id,
        "core_style": preferred_core_style,
        "representative_image_url": representative.image_url,
        "style_source_image_url": "",
        "supporting_post_ids": [item.post_id for item in cluster_sorted],
        "keywords": keywords,
        "normalized_tags": {
            field: top_counter_items(counter, limit=6)
            for field, counter in merged_tags.items()
        },
        "trend_score": trend_score,
        "confidence": confidence,
        "data_lifecycle": lifecycles["data_lifecycle"],
        "trend_lifecycle": lifecycles["trend_lifecycle"],
        "life_cycle": display_lifecycle,  # frontend display
        "reasoning_summary": " ".join(reasoning_parts),
        "status": recommend_trend_status(trend_score, support_count),
        "push_status": "not_pushed",
        "identified_at": now_iso(),
        "metrics": {
            "support_post_count": support_count,
            "core_style_tags": top_counter_items(style_counter, limit=6),
            "average_comment_coverage_rate": avg_coverage,
            "average_confidence_penalty": avg_confidence_penalty,
            "average_like_count": round(
                sum(item.like_count for item in cluster) / support_count, 2,
            ),
            "average_favorite_count": round(
                sum(item.favorite_count for item in cluster) / support_count, 2,
            ),
            "average_comment_count": round(
                sum(item.comment_count for item in cluster) / support_count, 2,
            ),
            "promotion_post_ratio": round(
                sum(
                    1
                    for item in cluster
                    if item.promotion_type not in {"unknown", "natural_ugc"}
                )
                / support_count,
                4,
            ),
            "engagement_score": engagement_score,
            "support_score": support_score,
            "velocity_score": velocity_metrics["velocity_score"],
            "recent_growth_ratio": velocity_metrics["recent_growth_ratio"],
            "recent_growth_slope": velocity_metrics["recent_growth_slope"],
            "recent_post_ratio": velocity_metrics["recent_post_ratio"],
            "high_growth_post_count": velocity_metrics["high_growth_post_count"],
            "comment_signal_score": comment_signal_score,
            "coverage_confidence_score": coverage_confidence_score,
            "signal_quality_distribution": quality_dist,
        },
        "comment_signal_summary": {
            "style_tags": top_counter_items(style_counter, limit=8),
            "style_tag_counts": top_counter_counts(style_counter, limit=8),
            "user_demands": top_counter_items(demand_counter, limit=8),
            "demand_signal_counts": top_counter_counts(demand_counter, limit=8),
            "pain_points": top_counter_items(pain_counter, limit=8),
            "pain_point_counts": top_counter_counts(pain_counter, limit=8),
            "social_proofs": top_counter_items(proof_counter, limit=8),
            "social_proof_counts": top_counter_counts(proof_counter, limit=8),
            "purchase_intents": top_counter_items(purchase_counter, limit=8),
            "purchase_intent_counts": top_counter_counts(purchase_counter, limit=8),
            "negative_feedbacks": top_counter_items(negative_counter, limit=8),
            "negative_signal_counts": top_counter_counts(negative_counter, limit=8),
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
                "signal_quality": item.signal_quality,
                "evidence_signals": {
                    "style_tags": sorted(item.style_tags)[:6],
                    "user_demands": sorted(item.demand_tags)[:6],
                    "pain_points": sorted(item.pain_points)[:6],
                    "social_proofs": sorted(item.social_proofs)[:6],
                    "purchase_intents": sorted(item.purchase_intents)[:6],
                    "negative_feedbacks": sorted(item.negative_feedbacks)[:6],
                },
            }
            for item in cluster_sorted[:10]
        ],
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def is_trend_candidate(signal: PostSignal) -> bool:
    if not signal.post_id:
        return False
    if signal.clean_status == "filtered":
        return False
    if signal.signal_quality == "discarded_low_signal":
        return False
    if not signal.normalized_tags and not signal.raw_tags:
        return False
    return True


def recommend_trend_status(trend_score: float, support_count: int) -> str:
    if trend_score >= 6.5 and support_count >= 3:
        return "promote"
    if trend_score >= 3.5:
        return "watch"
    return "discard"


def top_signal_keywords(signals: list[PostSignal], limit: int = 8) -> list[str]:
    counter: Counter[str] = Counter()
    for signal in signals:
        normalized_core_tags = (
            signal.normalized_tags.get("style_tags", set())
            | signal.normalized_tags.get("nail_technique", set())
        )
        for token in signal.raw_tags:
            normalized_token = normalize_phrase(token)
            if normalized_token.endswith("美甲") and len(normalized_token) > 2:
                trimmed = normalized_token[:-2].strip()
                if trimmed and trimmed in normalized_core_tags:
                    normalized_token = trimmed
            counter[normalized_token or token] += 1
        for token in signal.purchase_intents:
            counter[token] += 1
        for token in signal.social_proofs:
            counter[token] += 1
        for vals in signal.normalized_tags.values():
            for v in vals:
                counter[v] += 2
    return [item for item, _ in counter.most_common(limit)]


def top_counter_items(counter: Counter[str], limit: int = 8) -> list[str]:
    return [item for item, _ in counter.most_common(limit)]


def top_counter_counts(counter: Counter[str], limit: int = 8) -> list[dict[str, Any]]:
    return [{"label": item, "count": count} for item, count in counter.most_common(limit)]


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


def normalize_snapshots(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    snapshots: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        captured_at = str(item.get("captured_at") or "")
        snapshots.append(
            {
                "captured_at": captured_at,
                "like_count": int(item.get("like_count") or 0),
                "favorite_count": int(item.get("favorite_count") or 0),
                "comment_count": int(item.get("comment_count") or 0),
            }
        )
    return sorted(snapshots, key=lambda snap: snap["captured_at"])


def snapshot_hot_score(snapshot: dict[str, Any]) -> float:
    return (
        math.log1p(max(0, int(snapshot.get("like_count") or 0))) * 0.35
        + math.log1p(max(0, int(snapshot.get("favorite_count") or 0))) * 0.4
        + math.log1p(max(0, int(snapshot.get("comment_count") or 0))) * 0.25
    )


def compute_velocity_metrics(cluster: list[PostSignal]) -> dict[str, float | int]:
    if not cluster:
        return {
            "velocity_score": 0.0,
            "recent_growth_ratio": 0.0,
            "recent_growth_slope": 0.0,
            "recent_post_ratio": 0.0,
            "high_growth_post_count": 0,
        }

    growth_ratios: list[float] = []
    daily_slopes: list[float] = []
    high_growth_post_count = 0
    now = datetime.now(UTC)
    recent_post_ratio = (
        sum(
            1
            for item in cluster
            if (dt := parse_datetime(item.published_at))
            and (now - dt.astimezone(UTC)) <= timedelta(days=14)
        )
        / len(cluster)
    )

    for item in cluster:
        snapshots = item.snapshots
        if len(snapshots) < 2:
            continue
        latest = snapshots[-1]
        latest_dt = parse_datetime(latest.get("captured_at"))
        if not latest_dt:
            continue

        target_dt = latest_dt - timedelta(days=7)
        baseline = None
        for snap in reversed(snapshots[:-1]):
            snap_dt = parse_datetime(snap.get("captured_at"))
            if snap_dt and snap_dt <= target_dt:
                baseline = snap
                break
        if baseline is None:
            baseline = snapshots[0]

        baseline_dt = parse_datetime(baseline.get("captured_at"))
        if not baseline_dt:
            continue

        latest_score = snapshot_hot_score(latest)
        baseline_score = snapshot_hot_score(baseline)
        delta_days = max((latest_dt - baseline_dt).total_seconds() / 86400, 1 / 24)
        delta_score = max(0.0, latest_score - baseline_score)
        growth_ratio = delta_score / max(baseline_score, 1.0)
        daily_slope = delta_score / delta_days

        growth_ratios.append(growth_ratio)
        daily_slopes.append(daily_slope)
        if growth_ratio >= 0.25:
            high_growth_post_count += 1

    avg_growth_ratio = round(sum(growth_ratios) / len(growth_ratios), 4) if growth_ratios else 0.0
    avg_daily_slope = round(sum(daily_slopes) / len(daily_slopes), 4) if daily_slopes else 0.0
    velocity_score = round(
        min(
            10.0,
            avg_growth_ratio * 3.5
            + math.log1p(max(avg_daily_slope, 0.0)) * 1.8
            + recent_post_ratio * 2.0,
        ),
        4,
    )
    return {
        "velocity_score": velocity_score,
        "recent_growth_ratio": avg_growth_ratio,
        "recent_growth_slope": avg_daily_slope,
        "recent_post_ratio": round(recent_post_ratio, 4),
        "high_growth_post_count": high_growth_post_count,
    }


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
    if not text or len(text) == 1 or text in COMMON_STOPWORDS:
        return ""
    return text


def parse_datetime(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def now_iso() -> str:
    return datetime.now(UTC).astimezone().isoformat()
