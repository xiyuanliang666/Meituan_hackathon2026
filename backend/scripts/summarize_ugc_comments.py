#!/usr/bin/env python3
"""Fetch available Xiaohongshu comments and summarize them for trend analysis."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.prompts.ugc_comment_summary import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from app.services.multimodal_client import (
    MultimodalModelError,
    generate_text_json_with_gemini,
    generate_text_json_with_qwen,
    is_gemini_enabled,
    is_qwen_vl_enabled,
)

from backend.scripts.build_ugc_json_from_links import (
    DEFAULT_USER_AGENT,
    fetch_html,
    clean_text,
    extract_window_json_object,
)


ALLOWED_SENTIMENTS = {"positive", "mixed", "negative", "neutral", "unknown"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize UGC comment signals")
    parser.add_argument("--input", required=True, help="Input JSON path")
    parser.add_argument("--output", required=True, help="Output JSON path")
    parser.add_argument("--raw-comments-file", default="", help="Sidecar JSON path for raw comments")
    parser.add_argument("--limit", type=int, default=None, help="Only process first N posts")
    parser.add_argument("--post-id", default="", help="Only process the specified post_id")
    parser.add_argument("--force", action="store_true", help="Re-summarize posts even if already done")
    parser.add_argument("--resume", action="store_true", help="Skip posts whose comment summary is already done/unavailable")
    parser.add_argument("--from-start", action="store_true", help="Re-run summaries for all posts from the beginning")
    parser.add_argument(
        "--provider",
        choices=("auto", "qwen", "gemini", "mock"),
        default="auto",
        help="LLM provider selection",
    )
    parser.add_argument("--cookie", default="", help="Optional Cookie header for fetching pages")
    parser.add_argument("--user-agent", default="", help="Optional User-Agent for fetching pages")
    args = parser.parse_args()
    if args.resume and args.from_start:
        raise SystemExit("Cannot use --resume and --from-start at the same time")

    input_path = Path(args.input)
    output_path = Path(args.output)
    raw_comments_path = resolve_raw_comments_path(args.raw_comments_file, output_path)
    raw = json.loads(input_path.read_text(encoding="utf-8"))
    posts = raw.get("posts")
    if not isinstance(posts, list):
        raise SystemExit("Input JSON must contain a top-level 'posts' array")
    raw_comment_store = load_raw_comment_store(raw_comments_path)

    provider = resolve_provider(args.provider)
    processed = 0
    skipped = 0

    for post in posts:
        if not isinstance(post, dict):
            continue
        if args.post_id and str(post.get("post_id") or "") != args.post_id:
            continue
        ensure_comment_defaults(post)
        if args.resume and post["comment_insights"].get("status") in {"done", "unavailable"}:
            skipped += 1
            continue
        if post["comment_insights"].get("status") == "done" and not args.force and not args.from_start:
            skipped += 1
            continue
        if args.limit is not None and processed >= args.limit:
            break

        raw_comments = fetch_available_comments(
            post,
            raw_comment_store=raw_comment_store,
            cookie=args.cookie,
            user_agent=args.user_agent,
        )
        post["comment_sample_count"] = len(raw_comments)
        post["comment_fetch_status"] = "done" if raw_comments else "unavailable"
        delete_legacy_raw_comments(post)
        save_raw_comment_store(raw_comments_path, raw_comment_store)

        if raw_comments:
            result = summarize_comments(post, raw_comments, provider=provider)
        else:
            result = unavailable_comment_summary(post)
        post["comment_insights"] = result
        processed += 1
        print(f"[{processed}] {post.get('post_id')} comments={len(raw_comments)} status={result.get('status')}")
        output_path.write_text(json.dumps({"posts": posts}, ensure_ascii=False, indent=2), encoding="utf-8")

    output_path.write_text(json.dumps({"posts": posts}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"written: {output_path}")
    print(f"processed={processed} skipped={skipped} provider={provider}")


def resolve_provider(provider: str) -> str:
    if provider != "auto":
        return provider
    if is_qwen_vl_enabled():
        return "qwen"
    if is_gemini_enabled():
        return "gemini"
    return "mock"


def resolve_raw_comments_path(raw_comments_file: str, output_path: Path) -> Path:
    if raw_comments_file:
        return Path(raw_comments_file)
    return output_path.with_name(f"{output_path.stem}_raw_comments.json")


def load_raw_comment_store(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"posts": {}}
    if isinstance(payload, dict) and isinstance(payload.get("posts"), dict):
        return payload
    return {"posts": {}}


def save_raw_comment_store(path: Path, store: dict[str, Any]) -> None:
    path.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_comment_defaults(post: dict[str, Any]) -> None:
    post.setdefault("comment_sample_count", 0)
    post.setdefault("comment_fetch_status", "pending")
    post.setdefault(
        "comment_insights",
        {
            "status": "pending",
            "comment_summary": "",
            "summary": "",
            "estimated_total_comment_count": 0,
            "fetched_comment_count": 0,
            "comment_coverage_rate": 0.0,
            "sampling_strategy": [],
            "confidence_penalty": 0.0,
            "style_tags": [],
            "user_demands": [],
            "pain_points": [],
            "social_proofs": [],
            "purchase_intents": [],
            "negative_feedbacks": [],
            "risk_flags": [],
            "not_suitable_for": [],
            "failure_cases": [],
            "sentiment": "unknown",
            "positive_signals": [],
        },
    )


def delete_legacy_raw_comments(post: dict[str, Any]) -> None:
    post.pop("raw_comments", None)


def build_sampling_metadata(post: dict[str, Any], fetched_count: int) -> dict[str, Any]:
    estimated_total = int(post.get("comment_count") or 0)
    coverage_rate = 0.0
    if estimated_total > 0:
        coverage_rate = min(1.0, fetched_count / estimated_total)

    if fetched_count <= 0:
        confidence_penalty = 0.6
    elif coverage_rate >= 0.5:
        confidence_penalty = 0.0
    elif coverage_rate >= 0.3:
        confidence_penalty = 0.15
    else:
        confidence_penalty = 0.35

    return {
        "estimated_total_comment_count": estimated_total,
        "fetched_comment_count": fetched_count,
        "comment_coverage_rate": round(coverage_rate, 4),
        "sampling_strategy": [
            "platform_visible_comment_sampling",
            "priority_aware_comment_sampling",
            "top_liked_comment_priority",
            "latest_comment_priority",
            "threaded_comment_priority",
            "fallback_comment_sampling",
        ],
        "confidence_penalty": confidence_penalty,
    }


def fetch_available_comments(
    post: dict[str, Any],
    raw_comment_store: dict[str, Any],
    cookie: str = "",
    user_agent: str = "",
) -> list[dict[str, Any]]:
    post_id = str(post.get("post_id") or "")
    store_posts = raw_comment_store.get("posts")
    if isinstance(store_posts, dict) and post_id:
        stored = store_posts.get(post_id)
        if isinstance(stored, dict):
            comments = normalize_raw_comments(stored.get("raw_comments"))
            if comments:
                return comments

    source_url = str(post.get("source_url") or "")
    if not source_url:
        return []

    try:
        html = fetch_html(source_url, cookie=cookie, user_agent=user_agent or DEFAULT_USER_AGENT)
    except Exception:
        return normalize_raw_comments(post.get("raw_comments"))

    comments = extract_comments_from_initial_state(html)
    if comments:
        persist_raw_comments(raw_comment_store, post, comments, "done")
        return comments

    comments = extract_comments_from_dom(html)
    if comments:
        persist_raw_comments(raw_comment_store, post, comments, "done")
        return comments

    fallback_comments = normalize_raw_comments(post.get("raw_comments"))
    persist_raw_comments(raw_comment_store, post, fallback_comments, "done" if fallback_comments else "unavailable")
    return fallback_comments


def persist_raw_comments(
    raw_comment_store: dict[str, Any],
    post: dict[str, Any],
    comments: list[dict[str, Any]],
    fetch_status: str,
) -> None:
    store_posts = raw_comment_store.setdefault("posts", {})
    if not isinstance(store_posts, dict):
        raw_comment_store["posts"] = {}
        store_posts = raw_comment_store["posts"]
    post_id = str(post.get("post_id") or "")
    if not post_id:
        return
    store_posts[post_id] = {
        "post_id": post_id,
        "source_url": str(post.get("source_url") or ""),
        "comment_sample_count": len(comments),
        "comment_fetch_status": fetch_status,
        "raw_comments": comments,
    }


def extract_comments_from_initial_state(html: str) -> list[dict[str, Any]]:
    obj = extract_window_json_object(html, "window.__INITIAL_STATE__")
    if not isinstance(obj, dict):
        return []
    note_store = obj.get("note")
    if not isinstance(note_store, dict):
        return []
    detail_map = note_store.get("noteDetailMap")
    if not isinstance(detail_map, dict):
        return []

    results: list[dict[str, Any]] = []
    for detail in detail_map.values():
        if not isinstance(detail, dict):
            continue
        comments = detail.get("comments")
        if not isinstance(comments, dict):
            continue
        comment_list = comments.get("list")
        if not isinstance(comment_list, list):
            continue
        for item in comment_list:
            parsed = normalize_comment_item(item)
            if parsed:
                results.append(parsed)
    return dedupe_comments(results)


def extract_comments_from_dom(html: str) -> list[dict[str, Any]]:
    comment_blocks = re.findall(
        r'<div[^>]*class="[^"]*\bcomment-item\b[^"]*"[^>]*>(.*?)</div>\s*</div>|<div[^>]*class=\'[^\']*\bcomment-item\b[^\']*\'[^>]*>(.*?)</div>\s*</div>',
        html,
        flags=re.I | re.S,
    )
    results: list[dict[str, Any]] = []
    for a, b in comment_blocks:
        block = a or b
        content = clean_text(re.sub(r"<[^>]+>", " ", block))
        if not content:
            continue
        results.append({"author_name": "", "content": content, "like_count": 0})
    return dedupe_comments(results)


def normalize_comment_item(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None

    content = ""
    for key in ("content", "commentContent", "text"):
        value = item.get(key)
        if isinstance(value, str) and clean_text(value):
            content = clean_text(value)
            break
    if not content:
        return None

    author_name = ""
    user_info = item.get("userInfo") or item.get("user")
    if isinstance(user_info, dict):
        author_name = clean_text(str(user_info.get("nickname") or user_info.get("name") or ""))

    like_count = 0
    for key in ("likeCount", "likedCount"):
        value = item.get(key)
        if isinstance(value, (int, float)):
            like_count = int(value)
            break
        if isinstance(value, str):
            digits = re.search(r"(\d+(?:\.\d+)?)", value)
            if digits:
                like_count = int(float(digits.group(1)))
                break

    return {"author_name": author_name, "content": content, "like_count": like_count}


def normalize_raw_comments(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    results: list[dict[str, Any]] = []
    for item in raw:
        parsed = normalize_comment_item(item)
        if parsed:
            results.append(parsed)
    return dedupe_comments(results)


def dedupe_comments(comments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    output: list[dict[str, Any]] = []
    for item in comments:
        key = (str(item.get("author_name") or ""), str(item.get("content") or ""))
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def summarize_comments(post: dict[str, Any], comments: list[dict[str, Any]], provider: str) -> dict[str, Any]:
    sampling = build_sampling_metadata(post, len(comments))
    if provider == "mock":
        return mock_summary(post, comments)

    try:
        prompt = build_comment_prompt(post, comments)
        if provider == "qwen":
            data = generate_text_json_with_qwen(SYSTEM_PROMPT, prompt)
        else:
            data = generate_text_json_with_gemini(SYSTEM_PROMPT, prompt)
        normalized = normalize_comment_summary(data)
        normalized.update(sampling)
        return normalized
    except MultimodalModelError:
        return mock_summary(post, comments)


def build_comment_prompt(post: dict[str, Any], comments: list[dict[str, Any]]) -> str:
    sampling = build_sampling_metadata(post, len(comments))
    lines = []
    for index, comment in enumerate(comments[:40], start=1):
        author = str(comment.get("author_name") or "匿名用户")
        content = str(comment.get("content") or "")
        likes = int(comment.get("like_count") or 0)
        lines.append(f"{index}. {author}（赞{likes}）：{content}")
    comments_block = "\n".join(lines) if lines else "无可用评论"
    return USER_PROMPT_TEMPLATE.format(
        title=str(post.get("title") or ""),
        content=str(post.get("content") or ""),
        raw_tags=", ".join(str(tag) for tag in (post.get("raw_tags") or [])),
        estimated_total_comment_count=sampling["estimated_total_comment_count"],
        fetched_comment_count=sampling["fetched_comment_count"],
        comment_coverage_rate=sampling["comment_coverage_rate"],
        sampling_strategy=", ".join(sampling["sampling_strategy"]),
        comments_block=comments_block,
    )


def normalize_comment_summary(data: dict[str, Any]) -> dict[str, Any]:
    sentiment = str(data.get("sentiment") or "unknown").strip().lower()
    if sentiment not in ALLOWED_SENTIMENTS:
        sentiment = "unknown"
    comment_summary = clean_text(str(data.get("comment_summary") or data.get("summary") or ""))
    negative_feedbacks = normalize_string_list(data.get("negative_feedbacks"))
    failure_cases = normalize_string_list(data.get("failure_cases"))
    risk_flags = normalize_string_list(data.get("risk_flags"))
    positive_signals = normalize_string_list(data.get("positive_signals"))
    return {
        "status": "done",
        "comment_summary": comment_summary,
        "summary": comment_summary,
        "estimated_total_comment_count": int(data.get("estimated_total_comment_count") or 0),
        "fetched_comment_count": int(data.get("fetched_comment_count") or 0),
        "comment_coverage_rate": max(0.0, min(1.0, float(data.get("comment_coverage_rate") or 0.0))),
        "sampling_strategy": normalize_string_list(data.get("sampling_strategy")),
        "confidence_penalty": max(0.0, float(data.get("confidence_penalty") or 0.0)),
        "style_tags": normalize_string_list(data.get("style_tags")),
        "user_demands": normalize_string_list(data.get("user_demands")),
        "pain_points": normalize_string_list(data.get("pain_points")),
        "social_proofs": normalize_string_list(data.get("social_proofs")),
        "purchase_intents": normalize_string_list(data.get("purchase_intents")),
        "negative_feedbacks": dedupe_strings(negative_feedbacks + failure_cases + risk_flags),
        "risk_flags": risk_flags,
        "not_suitable_for": normalize_string_list(data.get("not_suitable_for")),
        "failure_cases": failure_cases,
        "sentiment": sentiment,
        "positive_signals": positive_signals,
    }


def unavailable_comment_summary(post: dict[str, Any]) -> dict[str, Any]:
    comment_count = int(post.get("comment_count") or 0)
    if comment_count > 0:
        summary = "页面显示该帖子存在评论，但当前抓取链路未拿到可解析评论文本，暂无法生成可靠评论摘要。"
    else:
        summary = "该帖子当前无可用评论样本。"
    sampling = build_sampling_metadata(post, 0)
    return {
        "status": "unavailable",
        "comment_summary": summary,
        "summary": summary,
        **sampling,
        "style_tags": [],
        "user_demands": [],
        "pain_points": [],
        "social_proofs": [],
        "purchase_intents": [],
        "negative_feedbacks": [],
        "risk_flags": [],
        "not_suitable_for": [],
        "failure_cases": [],
        "sentiment": "unknown",
        "positive_signals": [],
    }


def mock_summary(post: dict[str, Any], comments: list[dict[str, Any]]) -> dict[str, Any]:
    full_text = "\n".join(str(item.get("content") or "") for item in comments)
    lowered = full_text.lower()

    style_tags: list[str] = []
    user_demands: list[str] = []
    pain_points: list[str] = []
    social_proofs: list[str] = []
    purchase_intents: list[str] = []
    negative_feedbacks: list[str] = []
    risk_flags: list[str] = []
    not_suitable_for: list[str] = []
    failure_cases: list[str] = []
    positive_signals: list[str] = []

    if any(token in lowered for token in ("显手黄", "显黄", "黄皮慎重")):
        risk_flags.append("部分评论提到显手黄")
        not_suitable_for.append("黄皮手部")
        pain_points.append("担心显手黄或不适合黄皮")
        negative_feedbacks.append("存在显手黄相关反馈")
    if any(token in lowered for token in ("翻车", "不好看", "踩雷", "后悔")):
        failure_cases.append("存在翻车或踩雷反馈")
        negative_feedbacks.append("评论里出现翻车或踩雷反馈")
    if any(token in lowered for token in ("显白", "高级", "温柔", "好看", "绝")):
        positive_signals.append("评论中有较多正向反馈，如显白、好看或高级感")
        social_proofs.append("评论区对款式颜值和显白效果有较强共识")
    if any(token in lowered for token in ("难做", "复杂", "费时")):
        risk_flags.append("可能存在制作复杂或复刻难度较高的问题")
        pain_points.append("评论提到复刻难度或制作耗时")
    if any(token in lowered for token in ("求同款", "求教程", "求色号", "求链接", "求款式")):
        user_demands.append("用户在评论里主动索要同款、教程或细节信息")
    if any(token in lowered for token in ("想做", "想去做", "安排", "下次做", "我也要做")):
        purchase_intents.append("评论里出现明确的跟做或下次尝试意愿")
    if any(token in lowered for token in ("猫眼", "法式", "腮红", "裸色", "红色", "粉色", "银色", "钻", "渐变")):
        style_tags.append("评论中反复感知到具体颜色、工艺或风格元素")

    sentiment = "neutral"
    if positive_signals and (risk_flags or failure_cases):
        sentiment = "mixed"
    elif positive_signals:
        sentiment = "positive"
    elif risk_flags or failure_cases:
        sentiment = "negative"

    sampling = build_sampling_metadata(post, len(comments))
    if comments:
        summary = f"共抓到 {len(comments)} 条可解析评论。"
        if purchase_intents or user_demands:
            summary += " 评论里能看到跟做、求同款或求细节信息的需求。"
        if positive_signals or social_proofs:
            summary += " 也有比较集中的正向反馈。"
        if pain_points or risk_flags or failure_cases:
            summary += " 同时存在一些复刻或适配风险提示。"
    else:
        summary = "暂无可用评论样本。"

    return {
        "status": "done" if comments else "unavailable",
        "comment_summary": summary,
        "summary": summary,
        **sampling,
        "style_tags": dedupe_strings(style_tags),
        "user_demands": dedupe_strings(user_demands),
        "pain_points": dedupe_strings(pain_points),
        "social_proofs": dedupe_strings(social_proofs),
        "purchase_intents": dedupe_strings(purchase_intents),
        "negative_feedbacks": dedupe_strings(negative_feedbacks + failure_cases + risk_flags),
        "risk_flags": dedupe_strings(risk_flags),
        "not_suitable_for": dedupe_strings(not_suitable_for),
        "failure_cases": dedupe_strings(failure_cases),
        "sentiment": sentiment if comments else "unknown",
        "positive_signals": dedupe_strings(positive_signals),
    }


def normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    output = []
    for item in value:
        text = clean_text(str(item or ""))
        if text:
            output.append(text)
    return dedupe_strings(output)


def dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in values:
        if item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


if __name__ == "__main__":
    main()
