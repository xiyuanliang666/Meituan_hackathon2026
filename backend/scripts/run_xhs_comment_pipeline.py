#!/usr/bin/env python3
"""One-shot pipeline: fetch Xiaohongshu comments with Playwright, then summarize them.

Usage:
    python backend/scripts/run_xhs_comment_pipeline.py \
      --input backend/mock_data/ugc_posts_from_links.json \
      --output backend/mock_data/ugc_posts_from_links.json
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch XHS comments and summarize them in one command")
    parser.add_argument("--input", required=True, help="Input JSON path")
    parser.add_argument("--output", required=True, help="Output JSON path")
    parser.add_argument("--raw-comments-file", default="", help="Sidecar JSON path for raw comments")
    parser.add_argument("--user-data-dir", default="backend/.playwright-xhs-profile", help="Persistent browser profile")
    parser.add_argument("--limit", type=int, default=None, help="Only process first N posts")
    parser.add_argument("--comment-limit", type=int, default=20, help="Max comments per post for browser capture")
    parser.add_argument("--login-wait-seconds", type=int, default=60, help="Auto-wait time when login is required but no interactive TTY is available")
    parser.add_argument("--provider", choices=("auto", "qwen", "gemini", "mock"), default="auto")
    parser.add_argument("--force", action="store_true", help="Re-run summary even if comment_insights is already done")
    parser.add_argument("--resume", action="store_true", help="Continue from already-written progress")
    parser.add_argument("--from-start", action="store_true", help="Re-run the whole pipeline from the beginning")
    parser.add_argument("--headless", action="store_true", help="Run Playwright in headless mode")
    args = parser.parse_args()
    if args.resume and args.from_start:
        raise SystemExit("Cannot use --resume and --from-start at the same time")

    repo_root = Path(__file__).resolve().parents[2]
    backend_dir = Path(__file__).resolve().parents[1]
    input_path = (repo_root / args.input).resolve() if not Path(args.input).is_absolute() else Path(args.input)
    output_path = (repo_root / args.output).resolve() if not Path(args.output).is_absolute() else Path(args.output)
    raw_comments_path = (
        (repo_root / args.raw_comments_file).resolve()
        if args.raw_comments_file and not Path(args.raw_comments_file).is_absolute()
        else (Path(args.raw_comments_file).resolve() if args.raw_comments_file else output_path.with_name(f"{output_path.stem}_raw_comments.json"))
    )
    user_data_dir = (repo_root / args.user_data_dir).resolve() if not Path(args.user_data_dir).is_absolute() else Path(args.user_data_dir)

    node_bin = shutil.which("node")
    if not node_bin:
        raise SystemExit("node is not installed or not on PATH")

    npm_bin = shutil.which("npm")
    if not npm_bin:
        raise SystemExit("npm is not installed or not on PATH")

    if not (backend_dir / "node_modules" / "playwright").exists():
        raise SystemExit(
            "Playwright dependency is not installed. Run `cd backend && npm install && npx playwright install chromium` first."
        )

    posts = load_posts(output_path if output_path.exists() else input_path)
    post_ids = select_post_ids(posts, limit=args.limit, resume=args.resume, from_start=args.from_start)

    if not post_ids:
        print("No posts need processing.")
        return

    total = len(post_ids)
    for index, post_id in enumerate(post_ids, start=1):
        print(f"Step {index}/{total}: capture comments for {post_id}")
        comment_cmd = [
            node_bin,
            str(backend_dir / "scripts" / "fetch_xhs_comments_playwright.mjs"),
            "--input",
            str(output_path),
            "--output",
            str(output_path),
            "--raw-comments-file",
            str(raw_comments_path),
            "--user-data-dir",
            str(user_data_dir),
            "--comment-limit",
            str(args.comment_limit),
            "--login-wait-seconds",
            str(args.login_wait_seconds),
            "--post-id",
            post_id,
        ]
        if args.headless:
            comment_cmd.append("--headless")
        subprocess.run(comment_cmd, cwd=repo_root, check=True)

        print(f"Step {index}/{total}: summarize comments for {post_id}")
        summary_cmd = [
            sys.executable,
            str(backend_dir / "scripts" / "summarize_ugc_comments.py"),
            "--input",
            str(output_path),
            "--output",
            str(output_path),
            "--raw-comments-file",
            str(raw_comments_path),
            "--provider",
            args.provider,
            "--post-id",
            post_id,
        ]
        if args.force or args.from_start:
            summary_cmd.append("--force")
        subprocess.run(summary_cmd, cwd=repo_root, check=True)

    print(f"\nDone. Updated file: {output_path}")


def load_posts(path: Path) -> list[dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    posts = raw.get("posts")
    if not isinstance(posts, list):
        raise SystemExit("Input JSON must contain a top-level 'posts' array")
    return [post for post in posts if isinstance(post, dict)]


def select_post_ids(posts: list[dict], limit: int | None, resume: bool, from_start: bool) -> list[str]:
    selected: list[str] = []
    for post in posts:
        post_id = str(post.get("post_id") or "")
        if not post_id:
            continue
        fetch_status = str(post.get("comment_fetch_status") or "pending")
        summary_status = str((post.get("comment_insights") or {}).get("status") or "pending")
        if resume and fetch_status in {"done", "unavailable"} and summary_status in {"done", "unavailable"}:
            continue
        selected.append(post_id)
        if limit is not None and len(selected) >= limit:
            break
    return selected


if __name__ == "__main__":
    main()
