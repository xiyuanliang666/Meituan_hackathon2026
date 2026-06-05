#!/usr/bin/env python3
"""Build UGC import JSON from a list of Xiaohongshu links.

Best effort only:
- If the page is publicly fetchable, try to extract title/content/images/author/counts.
- If the page is blocked or fields are missing, still emit a valid skeleton item.

Usage:
  python backend/scripts/build_ugc_json_from_links.py \
    --input backend/mock_data/xhs_links.txt \
    --output backend/mock_data/ugc_posts_from_links.json

Optional:
  --cookie "a=b; c=d"
  --user-agent "..."
"""

from __future__ import annotations

import argparse
import copy
import json
import re
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

_CORE_TEXT_FIELDS = ("author_name", "title", "content", "published_at")
_CORE_LIST_FIELDS = ("image_urls", "raw_tags")
_COUNT_FIELDS = ("like_count", "favorite_count", "comment_count")
_UGC_METADATA_DEFAULTS: dict[str, Any] = {
    "classification_status": "pending",
    "classification_model": "",
    "classified_at": "",
    "classification_confidence": 0.0,
    "is_nail_related": None,
    "category_guess": "unknown",
    "is_promotional": None,
    "promotion_type": "unknown",
    "promotion_confidence": 0.0,
    "clean_status": "pending",
    "clean_reason": "",
    "trend_weight": 1.0,
    "comment_insights": {
        "status": "pending",
        "summary": "",
        "risk_flags": [],
        "not_suitable_for": [],
        "failure_cases": [],
        "sentiment": "unknown",
        "positive_signals": [],
    },
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build UGC JSON from Xiaohongshu links")
    parser.add_argument("--input", required=True, help="Text file with one URL per line")
    parser.add_argument("--output", required=True, help="Output JSON path")
    parser.add_argument("--cookie", default="", help="Optional Cookie header for fetching pages")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT, help="Optional User-Agent")
    parser.add_argument(
        "--refresh-ttl-hours",
        type=int,
        default=72,
        help="Skip re-fetch for healthy posts fetched within the last N hours; use 0 to disable TTL cache",
    )
    parser.add_argument(
        "--only-missing",
        action="store_true",
        help="Only fetch posts whose existing content is incomplete or previously failed",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Force re-fetch every link and ignore local TTL/missing heuristics",
    )
    parser.add_argument(
        "--published-at-fallback",
        default=_now_iso(),
        help="Fallback ISO datetime when publish time cannot be extracted",
    )
    parser.add_argument(
        "--captured-at",
        default=_now_iso(),
        help="Snapshot capture time for this run; only used when interaction counts changed",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    existing_posts = load_existing_posts(output_path)

    urls: list[str] = []
    for raw_line in input_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line)
    posts: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for index, url in enumerate(urls, start=1):
        seen_urls.add(url)
        existing = existing_posts.get(url)
        if existing and not should_refetch(
            existing,
            force_refresh=args.force_refresh,
            only_missing=args.only_missing,
            refresh_ttl_hours=args.refresh_ttl_hours,
        ):
            reused = ensure_post_defaults(existing)
            posts.append(reused)
            print(f"[{index}/{len(urls)}] cached {url}")
            continue

        try:
            html = fetch_html(url, cookie=args.cookie, user_agent=args.user_agent)
            extracted = extract_from_html(url, html, fallback_published_at=args.published_at_fallback)
            extracted["last_fetched_at"] = args.captured_at
            print(f"[{index}/{len(urls)}] fetched {url}")
        except Exception as exc:
            extracted = build_skeleton(url, fallback_published_at=args.published_at_fallback)
            extracted["title"] = extracted["title"] or f"待补标题 {index}"
            extracted["content"] = extracted["content"] or ""
            extracted["last_fetched_at"] = args.captured_at
            print(f"[{index}/{len(urls)}] fallback {url}: {exc}")
        merged = merge_with_existing(
            existing,
            extracted,
            captured_at=args.captured_at,
        )
        posts.append(merged)

    # Preserve previously captured posts that were not part of this seed batch.
    for url, existing in existing_posts.items():
        if url in seen_urls:
            continue
        posts.append(ensure_post_defaults(existing))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps({"posts": posts}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"written: {output_path}")


def fetch_html(url: str, cookie: str = "", user_agent: str = DEFAULT_USER_AGENT) -> str:
    req = Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://www.xiaohongshu.com/",
            **({"Cookie": cookie} if cookie else {}),
        },
    )
    with urlopen(req, timeout=20) as resp:
        content_type = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(content_type, errors="ignore")


def extract_from_html(url: str, html: str, fallback_published_at: str) -> dict[str, Any]:
    item = build_skeleton(url, fallback_published_at=fallback_published_at)

    # First use page-structure-specific extraction for current Xiaohongshu note pages.
    fill_from_dom(item, html)

    meta_title = extract_meta(html, "og:title") or extract_meta(html, "twitter:title")
    meta_desc = extract_meta(html, "og:description") or extract_meta(html, "description")
    meta_images = extract_all_meta(html, "og:image")

    if meta_title and (not item["title"] or item["title"] == "待补标题"):
        item["title"] = clean_text(meta_title)
    if meta_desc and not is_generic_xhs_placeholder(meta_desc) and (
        not item["content"] or is_generic_xhs_placeholder(item["content"])
    ):
        item["content"] = clean_text(meta_desc)
    if meta_images and not item["image_urls"]:
        item["image_urls"] = dedupe_keep_order(meta_images)

    # Best-effort JSON extraction from embedded scripts.
    embedded_json_objects = extract_embedded_json_objects(html)
    for obj in embedded_json_objects:
        fill_from_json(item, obj)

    item["author_name"] = item["author_name"] or "待补作者"
    item["title"] = item["title"] or "待补标题"
    final_content, final_tags = split_content_and_hash_tags(item["content"] or "")
    item["content"] = final_content
    if final_tags:
        item["raw_tags"] = dedupe_keep_order(item["raw_tags"] + final_tags)
    item["raw_tags"] = dedupe_keep_order(item["raw_tags"])
    item["image_urls"] = dedupe_keep_order(item["image_urls"])

    # Fix 1: Assess fetch quality. Mark as ok only if we got real content.
    has_title = bool(item["title"] and item["title"] != "待补标题")
    has_content = bool(item["content"] and item["content"] != "待补标题")
    has_images = bool(item["image_urls"])
    if has_title and has_content and has_images:
        item["fetch_status"] = "ok"
    elif has_content and has_title:
        item["fetch_status"] = "ok"
    elif has_content:
        item["fetch_status"] = "ok"
    elif has_title:
        # Only title, no content — likely a restricted page
        item["fetch_status"] = "title_only"
    # else: keep the default "failed_or_login_wall" from build_skeleton

    return item


def build_skeleton(url: str, fallback_published_at: str) -> dict[str, Any]:
    note_id = extract_note_id(url) or f"manual-{abs(hash(url)) % 10**10}"
    item = {
        "post_id": f"xhs-{note_id}",
        "source": "xiaohongshu",
        "source_url": url,
        "author_name": "",
        "title": "",
        "content": "",
        "image_urls": [],
        "published_at": fallback_published_at,
        "like_count": 0,
        "favorite_count": 0,
        "comment_count": 0,
        "raw_tags": [],
        "snapshots": [],
        # Fix 1: default fetch status; overridden on success
        "fetch_status": "failed_or_login_wall",
    }
    return ensure_post_defaults(item)


def ensure_post_defaults(item: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(item)
    for key, default_value in _UGC_METADATA_DEFAULTS.items():
        if key not in normalized:
            normalized[key] = copy.deepcopy(default_value)
    if "last_fetched_at" not in normalized:
        normalized["last_fetched_at"] = ""
    normalized["snapshots"] = normalize_snapshots(normalized.get("snapshots"))
    return normalized


def normalize_snapshots(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    snapshots: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        snapshots.append(
            {
                "captured_at": str(item.get("captured_at") or ""),
                "like_count": int(item.get("like_count") or 0),
                "favorite_count": int(item.get("favorite_count") or 0),
                "comment_count": int(item.get("comment_count") or 0),
            }
        )
    return snapshots


def load_existing_posts(output_path: Path) -> dict[str, dict[str, Any]]:
    if not output_path.exists():
        return {}
    try:
        raw = json.loads(output_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    posts = raw.get("posts")
    if not isinstance(posts, list):
        return {}
    loaded: dict[str, dict[str, Any]] = {}
    for item in posts:
        if not isinstance(item, dict):
            continue
        normalized = ensure_post_defaults(item)
        source_url = str(normalized.get("source_url") or "")
        if source_url:
            loaded[source_url] = normalized
    return loaded


def merge_with_existing(existing: dict[str, Any] | None, fresh: dict[str, Any], captured_at: str) -> dict[str, Any]:
    merged = ensure_post_defaults(fresh)
    if not existing:
        return merged

    existing = ensure_post_defaults(existing)

    for field in _CORE_TEXT_FIELDS:
        if not merged.get(field):
            merged[field] = existing.get(field, "")

    for field in _CORE_LIST_FIELDS:
        if not merged.get(field):
            merged[field] = copy.deepcopy(existing.get(field, []))

    for field in _COUNT_FIELDS:
        merged_value = int(merged.get(field) or 0)
        existing_value = int(existing.get(field) or 0)
        if merged_value <= 0 < existing_value:
            merged[field] = existing_value

    for key in _UGC_METADATA_DEFAULTS:
        if key == "comment_insights":
            merged[key] = copy.deepcopy(existing.get(key) or _UGC_METADATA_DEFAULTS[key])
        elif key not in merged or merged.get(key) in (None, "", "unknown", "pending", 0.0):
            existing_value = existing.get(key)
            if existing_value not in (None, "", "unknown", "pending", 0.0):
                merged[key] = copy.deepcopy(existing_value)

    merged["snapshots"] = copy.deepcopy(existing.get("snapshots", []))

    previous_counts = tuple(int(existing.get(field) or 0) for field in _COUNT_FIELDS)
    current_counts = tuple(int(merged.get(field) or 0) for field in _COUNT_FIELDS)
    if current_counts != previous_counts:
        merged["snapshots"].append(
            {
                "captured_at": captured_at,
                "like_count": current_counts[0],
                "favorite_count": current_counts[1],
                "comment_count": current_counts[2],
            }
        )

    return merged


def should_refetch(
    existing: dict[str, Any],
    *,
    force_refresh: bool,
    only_missing: bool,
    refresh_ttl_hours: int,
) -> bool:
    if force_refresh:
        return True

    normalized = ensure_post_defaults(existing)
    if only_missing:
        return is_incomplete_post(normalized)

    if is_incomplete_post(normalized):
        return True

    if refresh_ttl_hours <= 0:
        return True

    fetched_at = parse_iso_datetime(str(normalized.get("last_fetched_at") or ""))
    if fetched_at is None:
        return True

    age_hours = (_now_datetime() - fetched_at).total_seconds() / 3600
    return age_hours >= refresh_ttl_hours


def is_incomplete_post(post: dict[str, Any]) -> bool:
    fetch_status = str(post.get("fetch_status") or "")
    title = str(post.get("title") or "").strip()
    content = str(post.get("content") or "").strip()
    images = post.get("image_urls") or []
    if fetch_status not in {"ok", "title_only"}:
        return True
    if not title or title == "待补标题":
        return True
    if not content:
        return True
    if not isinstance(images, list) or not images:
        return True
    return False


def parse_iso_datetime(value: str) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def fill_from_json(item: dict[str, Any], obj: Any) -> None:
    if not isinstance(obj, dict):
        return

    xhs_note = extract_xhs_note_from_initial_state(obj)
    if xhs_note:
        fill_from_xhs_note(item, xhs_note)

    for key in ("title", "desc", "content"):
        value = find_first_text(obj, key)
        if value and not item["content"]:
            if key == "title" and not item["title"]:
                item["title"] = clean_text(value)
            elif key != "title":
                content_text, content_tags = split_content_and_hash_tags(clean_text(value))
                item["content"] = content_text
                if content_tags:
                    item["raw_tags"] = dedupe_keep_order(item["raw_tags"] + content_tags)

    if not item["title"]:
        title = find_first_text(obj, "title")
        if title:
            item["title"] = clean_text(title)

    nickname = find_first_text(obj, "nickname") or find_first_text(obj, "author")
    if nickname and not item["author_name"]:
        item["author_name"] = clean_text(nickname)

    publish_time = find_first_text(obj, "time") or find_first_text(obj, "publishTime")
    if publish_time:
        normalized = normalize_published_at(publish_time)
        if normalized:
            item["published_at"] = normalized

    like_count = find_first_number(obj, ("likedCount", "like_count", "likes"))
    fav_count = find_first_number(obj, ("collectedCount", "favorite_count", "favorites"))
    comment_count = find_first_number(obj, ("commentCount", "comment_count", "comments"))
    if like_count is not None:
        item["like_count"] = max(item["like_count"], like_count)
    if fav_count is not None:
        item["favorite_count"] = max(item["favorite_count"], fav_count)
    if comment_count is not None:
        item["comment_count"] = max(item["comment_count"], comment_count)

    tags = find_all_texts(obj, {"tag", "tags", "keyword", "keywords"})
    if tags:
        item["raw_tags"] = dedupe_keep_order(item["raw_tags"] + [clean_text(t) for t in tags if clean_text(t)])

    images = find_all_image_urls(obj)
    if images:
        item["image_urls"] = dedupe_keep_order(item["image_urls"] + images)


def extract_xhs_note_from_initial_state(obj: dict[str, Any]) -> dict[str, Any] | None:
    note_store = obj.get("note")
    if not isinstance(note_store, dict):
        return None
    detail_map = note_store.get("noteDetailMap")
    if not isinstance(detail_map, dict) or not detail_map:
        return None
    for _, detail in detail_map.items():
        if not isinstance(detail, dict):
            continue
        note = detail.get("note")
        if isinstance(note, dict):
            return note
    return None


def fill_from_xhs_note(item: dict[str, Any], note: dict[str, Any]) -> None:
    title = clean_text(note.get("title", ""))
    if title:
        item["title"] = title

    desc = clean_text(note.get("desc", ""))
    if desc:
        desc_text, desc_tags = split_content_and_hash_tags(desc)
        item["content"] = desc_text
        if desc_tags:
            item["raw_tags"] = dedupe_keep_order(item["raw_tags"] + desc_tags)

    user = note.get("user")
    if isinstance(user, dict):
        nickname = clean_text(user.get("nickname", ""))
        if nickname:
            item["author_name"] = nickname

    published_at = normalize_published_at(note.get("time"))
    if published_at:
        item["published_at"] = published_at

    interact = note.get("interactInfo")
    if isinstance(interact, dict):
        item["like_count"] = parse_count(str(interact.get("likedCount", item["like_count"])))
        item["favorite_count"] = parse_count(str(interact.get("collectedCount", item["favorite_count"])))
        item["comment_count"] = parse_count(str(interact.get("commentCount", item["comment_count"])))

    tag_list = note.get("tagList")
    if isinstance(tag_list, list):
        extracted_tags = []
        for tag in tag_list:
            if isinstance(tag, dict):
                name = clean_text(tag.get("name", ""))
                if name:
                    extracted_tags.append(name)
        if extracted_tags:
            item["raw_tags"] = dedupe_keep_order(extracted_tags)

    image_list = note.get("imageList")
    if isinstance(image_list, list):
        urls: list[str] = []
        for image in image_list:
            if not isinstance(image, dict):
                continue
            for key in ("urlDefault", "urlPre", "url"):
                value = image.get(key)
                if isinstance(value, str) and value:
                    urls.append(value.replace("\\u002F", "/"))
            info_list = image.get("infoList")
            if isinstance(info_list, list):
                for info in info_list:
                    if isinstance(info, dict):
                        value = info.get("url")
                        if isinstance(value, str) and value:
                            urls.append(value.replace("\\u002F", "/"))
        if urls:
            item["image_urls"] = dedupe_keep_order(urls)


def fill_from_dom(item: dict[str, Any], html: str) -> None:
    author = extract_username(html)
    if author:
        item["author_name"] = author

    content = extract_note_content(html)
    if content:
        item["content"] = content

    title = extract_page_title(html)
    if title and (not item["title"] or " - 小红书" in item["title"]):
        item["title"] = title

    published_at = extract_publish_date(html)
    if published_at:
        item["published_at"] = published_at

    counts = extract_interaction_counts(html)
    item["like_count"] = counts["like_count"]
    item["favorite_count"] = counts["favorite_count"]
    item["comment_count"] = counts["comment_count"]

    raw_tags = extract_hash_tags(html)
    if raw_tags:
        item["raw_tags"] = dedupe_keep_order(raw_tags)


def extract_username(html: str) -> str:
    patterns = [
        r'<span[^>]*class="[^"]*\busername\b[^"]*"[^>]*>(.*?)</span>',
        r"<span[^>]*class='[^']*\busername\b[^']*'[^>]*>(.*?)</span>",
    ]
    return clean_html_text(first_match(patterns, html))


def extract_note_content(html: str) -> str:
    detail = extract_element_by_id(html, "detail-desc")
    if not detail:
        return ""

    note_texts = re.findall(
        r'<span[^>]*class="[^"]*\bnote-text\b[^"]*"[^>]*>(.*?)</span>|<span[^>]*class=\'[^\']*\bnote-text\b[^\']*\'[^>]*>(.*?)</span>',
        detail,
        flags=re.I | re.S,
    )
    texts = [clean_html_text(a or b) for a, b in note_texts if clean_html_text(a or b)]
    if texts:
        return " ".join(texts)
    return ""


def extract_page_title(html: str) -> str:
    title = clean_html_text(first_match([r"<title>(.*?)</title>"], html))
    if title.endswith(" - 小红书"):
        title = title[:-6].strip()
    return title


def extract_publish_date(html: str) -> str:
    bottom = first_match(
        [
            r'<div[^>]*class="[^"]*\bbottom-container\b[^"]*"[^>]*>(.*?)</div>',
            r"<div[^>]*class='[^']*\bbottom-container\b[^']*'[^>]*>(.*?)</div>",
        ],
        html,
        flags=re.I | re.S,
    )
    date_text = clean_html_text(
        first_match(
            [
                r'<span[^>]*class="[^"]*\bdate\b[^"]*"[^>]*>(.*?)</span>',
                r"<span[^>]*class='[^']*\bdate\b[^']*'[^>]*>(.*?)</span>",
            ],
            bottom or html,
            flags=re.I | re.S,
        )
    )
    return normalize_published_at(date_text)


def extract_interaction_counts(html: str) -> dict[str, int]:
    return {
        "like_count": parse_count(
            clean_html_text(
                first_match(
                    [
                        r'<div[^>]*class="[^"]*\blike-wrapper\b[^"]*"[^>]*>.*?<span[^>]*class="[^"]*\bcount\b[^"]*"[^>]*>(.*?)</span>',
                        r'<div[^>]*class="[^"]*\blike-active\b[^"]*"[^>]*>.*?<span[^>]*class="[^"]*\bcount\b[^"]*"[^>]*>(.*?)</span>',
                        r"<div[^>]*class='[^']*\blike-wrapper\b[^']*'[^>]*>.*?<span[^>]*class='[^']*\bcount\b[^']*'[^>]*>(.*?)</span>",
                        r"<div[^>]*class='[^']*\blike-active\b[^']*'[^>]*>.*?<span[^>]*class='[^']*\bcount\b[^']*'[^>]*>(.*?)</span>",
                    ],
                    html,
                    flags=re.I | re.S,
                )
            )
        ),
        "favorite_count": parse_count(
            clean_html_text(
                first_match(
                    [
                        r'<div[^>]*id="note-page-collect-board-guide"[^>]*>.*?<span[^>]*class="[^"]*\bcount\b[^"]*"[^>]*>(.*?)</span>',
                        r"<div[^>]*id='note-page-collect-board-guide'[^>]*>.*?<span[^>]*class='[^']*\bcount\b[^']*'[^>]*>(.*?)</span>",
                    ],
                    html,
                    flags=re.I | re.S,
                )
            )
        ),
        "comment_count": parse_count(
            clean_html_text(
                first_match(
                    [
                        r'<div[^>]*class="[^"]*\bchat-wrapper\b[^"]*"[^>]*>.*?<span[^>]*class="[^"]*\bcount\b[^"]*"[^>]*>(.*?)</span>',
                        r"<div[^>]*class='[^']*\bchat-wrapper\b[^']*'[^>]*>.*?<span[^>]*class='[^']*\bcount\b[^']*'[^>]*>(.*?)</span>",
                    ],
                    html,
                    flags=re.I | re.S,
                )
            )
        ),
    }


def extract_hash_tags(html: str) -> list[str]:
    detail = extract_element_by_id(html, "detail-desc")
    if not detail:
        return []

    tags = re.findall(
        r'<[^>]*class="[^"]*\bhash-tag\b[^"]*\btag\b[^"]*"[^>]*>(.*?)</[^>]+>|<[^>]*class=\'[^\']*\bhash-tag\b[^\']*\btag\b[^\']*\'[^>]*>(.*?)</[^>]+>',
        detail,
        flags=re.I | re.S,
    )
    output: list[str] = []
    for a, b in tags:
        text = clean_html_text(a or b).lstrip("#").strip()
        if text:
            output.append(text)
    return dedupe_keep_order(output)


def extract_element_by_id(html: str, element_id: str) -> str:
    patterns = [
        rf'<[^>]*id="{re.escape(element_id)}"[^>]*>(.*?)</[^>]+>',
        rf"<[^>]*id='{re.escape(element_id)}'[^>]*>(.*?)</[^>]+>",
    ]
    return first_match(patterns, html, flags=re.I | re.S)


def first_match(patterns: list[str], text: str, flags: int = 0) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags=flags)
        if match:
            return match.group(1)
    return ""


def clean_html_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return clean_text(text)


def split_content_and_hash_tags(text: str) -> tuple[str, list[str]]:
    if not text:
        return "", []

    tags: list[str] = []

    def _replace_topic(match: re.Match[str]) -> str:
        tag_text = clean_text(match.group(1))
        if tag_text:
            tags.append(tag_text)
        return " "

    stripped = re.sub(r"#([^#\n\r]+?)\[(?:话题|超话)\]#", _replace_topic, text)

    def _replace_plain(match: re.Match[str]) -> str:
        tag_text = clean_text(match.group(1))
        if tag_text:
            tags.append(tag_text)
        return " "

    stripped = re.sub(r"#([^#\n\r]{1,40}?)#", _replace_plain, stripped)
    stripped = clean_text(stripped.replace("[话题]", " ").replace("[超话]", " "))
    return stripped, dedupe_keep_order(tags)


def is_generic_xhs_placeholder(text: str) -> bool:
    normalized = clean_text(text)
    return normalized in {
        "3 亿人的生活经验，都在小红书",
        "3亿人的生活经验，都在小红书",
        "小红书",
    }


def parse_count(text: str) -> int:
    text = clean_text(text).lower()
    if not text:
        return 0
    text = text.replace(",", "")
    try:
        if text.endswith("万"):
            return int(float(text[:-1]) * 10000)
        if text.endswith("千"):
            return int(float(text[:-1]) * 1000)
        if text.endswith("w"):
            return int(float(text[:-1]) * 10000)
        if text.endswith("k"):
            return int(float(text[:-1]) * 1000)
        return int(float(text))
    except ValueError:
        match = re.search(r"(\d+(?:\.\d+)?)", text)
        if not match:
            return 0
        return int(float(match.group(1)))


def extract_embedded_json_objects(html: str) -> list[Any]:
    results: list[Any] = []

    for var_name in ("window.__INITIAL_STATE__", "window.__INITIAL_SSR_STATE__", "__INITIAL_STATE__"):
        extracted = extract_window_json_object(html, var_name)
        if extracted is not None:
            results.append(extracted)

    script_blocks = re.findall(r"<script[^>]*>(.*?)</script>", html, flags=re.I | re.S)
    for block in script_blocks:
        text = block.strip()
        if not text:
            continue

        for pattern in (
            r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;",
            r"window\.__INITIAL_SSR_STATE__\s*=\s*(\{.*?\})\s*;",
            r"__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;",
        ):
            for match in re.finditer(pattern, text, flags=re.S):
                try:
                    results.append(json.loads(match.group(1)))
                except json.JSONDecodeError:
                    pass

        if text.startswith("{") and text.endswith("}"):
            try:
                results.append(json.loads(text))
            except json.JSONDecodeError:
                pass

    return results


def extract_window_json_object(html: str, var_name: str) -> Any | None:
    marker = f"{var_name}="
    start = html.find(marker)
    if start < 0:
        return None
    brace_start = html.find("{", start)
    if brace_start < 0:
        return None

    depth = 0
    in_string = False
    escaped = False
    for index in range(brace_start, len(html)):
        char = html[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                raw = html[brace_start:index + 1]
                try:
                    return json.loads(normalize_js_object_text(raw))
                except json.JSONDecodeError:
                    return None
    return None


def normalize_js_object_text(raw: str) -> str:
    normalized = raw
    normalized = re.sub(r":\s*undefined\b", ": null", normalized)
    normalized = re.sub(r":\s*NaN\b", ": null", normalized)
    normalized = re.sub(r":\s*Infinity\b", ": null", normalized)
    normalized = re.sub(r":\s*-Infinity\b", ": null", normalized)
    return normalized


def extract_meta(html: str, name: str) -> str:
    patterns = [
        rf'<meta[^>]+property=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']+)["\']',
        rf'<meta[^>]+name=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']+)["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, flags=re.I)
        if match:
            return unescape(match.group(1)).strip()
    return ""


def extract_all_meta(html: str, name: str) -> list[str]:
    patterns = [
        rf'<meta[^>]+property=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']+)["\']',
        rf'<meta[^>]+name=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']+)["\']',
    ]
    output: list[str] = []
    for pattern in patterns:
        output.extend(unescape(m).strip() for m in re.findall(pattern, html, flags=re.I))
    return dedupe_keep_order(output)


def extract_note_id(url: str) -> str:
    path = urlparse(url).path.strip("/")
    parts = [p for p in path.split("/") if p]
    if not parts:
        return ""
    if "explore" in parts:
        idx = parts.index("explore")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return parts[-1]


def normalize_published_at(raw: str) -> str:
    if isinstance(raw, (int, float)):
        try:
            ts = float(raw)
            if ts > 10_000_000_000:
                ts /= 1000.0
            return datetime.fromtimestamp(ts, timezone.utc).astimezone().isoformat(timespec="seconds")
        except (OverflowError, OSError, ValueError):
            return ""

    text = clean_text(raw)
    if not text:
        return ""
    if text.startswith("编辑于 "):
        text = text.replace("编辑于 ", "", 1).strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}T", text):
        return text
    if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        return text + "T00:00:00+08:00"
    if re.match(r"^\d{4}/\d{2}/\d{2}$", text):
        return text.replace("/", "-") + "T00:00:00+08:00"
    if re.match(r"^\d{2}-\d{2}$", text):
        current_year = datetime.now().year
        return f"{current_year}-{text}T00:00:00+08:00"
    return ""


def find_first_text(obj: Any, target_key: str) -> str:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == target_key and isinstance(value, (str, int, float)):
                return str(value)
            result = find_first_text(value, target_key)
            if result:
                return result
    elif isinstance(obj, list):
        for item in obj:
            result = find_first_text(item, target_key)
            if result:
                return result
    return ""


def find_first_number(obj: Any, target_keys: tuple[str, ...]) -> int | None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in target_keys and isinstance(value, (int, float)):
                return int(value)
            result = find_first_number(value, target_keys)
            if result is not None:
                return result
    elif isinstance(obj, list):
        for item in obj:
            result = find_first_number(item, target_keys)
            if result is not None:
                return result
    return None


def find_all_texts(obj: Any, fuzzy_keys: set[str]) -> list[str]:
    output: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            normalized = key.lower()
            if any(k in normalized for k in fuzzy_keys):
                if isinstance(value, str):
                    output.append(value)
                elif isinstance(value, list):
                    output.extend(str(v) for v in value if isinstance(v, (str, int, float)))
            output.extend(find_all_texts(value, fuzzy_keys))
    elif isinstance(obj, list):
        for item in obj:
            output.extend(find_all_texts(item, fuzzy_keys))
    return output


def find_all_image_urls(obj: Any) -> list[str]:
    output: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            normalized = key.lower()
            if "image" in normalized or "url" in normalized:
                if isinstance(value, str) and is_image_url(value):
                    output.append(value)
                elif isinstance(value, list):
                    output.extend(v for v in value if isinstance(v, str) and is_image_url(v))
            output.extend(find_all_image_urls(value))
    elif isinstance(obj, list):
        for item in obj:
            output.extend(find_all_image_urls(item))
    return dedupe_keep_order(output)


def is_image_url(text: str) -> bool:
    lower = text.lower()
    return lower.startswith("http") and any(ext in lower for ext in (".jpg", ".jpeg", ".png", ".webp"))


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(str(text))).strip()


def dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        value = value.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _now_datetime() -> datetime:
    return datetime.now(timezone.utc).astimezone()


if __name__ == "__main__":
    main()
