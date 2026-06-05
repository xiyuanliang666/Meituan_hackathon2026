from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from app.services.business_db import (
    append_trend_pipeline_run_log,
    create_trend_run,
    get_trend_run,
    import_ugc_posts,
    list_trends,
    update_trend_pipeline_run,
)
from app.services.trend_jobs import execute_trend_run
from app.services.trend_materialization import convert_trend_to_draft


def execute_trend_pipeline(
    *,
    pipeline_run_id: str,
    input_json_path: str,
    output_json_path: str,
    raw_comments_file: str,
    inline_posts: list[dict[str, Any]] | None,
    seed_links: list[str] | None,
    user_data_dir: str,
    provider: str,
    limit: int | None,
    refresh_ttl_hours: int,
    only_missing: bool,
    force_refresh: bool,
    comment_limit: int,
    login_wait_seconds: int,
    min_support: int,
    max_trends: int,
    resume: bool,
    from_start: bool,
    force_summary: bool,
    headless: bool,
    auto_convert_to_draft: bool,
    convert_limit: int,
    merchant_id: str,
    use_trend_tags: bool,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    backend_dir = Path(__file__).resolve().parents[2]
    input_path = _resolve_repo_path(repo_root, input_json_path)
    output_path = _resolve_repo_path(repo_root, output_json_path)
    raw_comments_path = _resolve_repo_path(repo_root, raw_comments_file)
    user_data_path = _resolve_repo_path(repo_root, user_data_dir)

    try:
        if inline_posts:
            posts = [post for post in inline_posts if isinstance(post, dict)]
            total_posts = len(posts)
            update_trend_pipeline_run(
                pipeline_run_id,
                status="running",
                stage="import_posts",
                total_posts=total_posts,
                processed_posts=_count_completed_posts(posts),
                error_message="",
                payload={"source_mode": "inline_posts"},
            )
            append_trend_pipeline_run_log(pipeline_run_id, f"Using inline mock posts: total_posts={total_posts}")
        else:
            if seed_links:
                normalized_links = [str(item).strip() for item in seed_links if str(item).strip()]
                update_trend_pipeline_run(
                    pipeline_run_id,
                    status="running",
                    stage="build_posts",
                    total_posts=len(normalized_links),
                    error_message="",
                    payload={"source_mode": "seed_links"},
                )
                append_trend_pipeline_run_log(pipeline_run_id, f"Build posts from seed links: count={len(normalized_links)}")
                _build_posts_from_seed_links(
                    repo_root=repo_root,
                    backend_dir=backend_dir,
                    seed_links=normalized_links,
                    output_path=output_path,
                    refresh_ttl_hours=refresh_ttl_hours,
                    only_missing=only_missing,
                    force_refresh=force_refresh,
                )

            total_posts = _count_posts(input_path if seed_links else output_path if output_path.exists() else input_path)
            update_trend_pipeline_run(
                pipeline_run_id,
                status="running",
                stage="comment_pipeline",
                total_posts=total_posts,
                error_message="",
                payload={"source_mode": "seed_links" if seed_links else "json_path"},
            )
            append_trend_pipeline_run_log(
                pipeline_run_id,
                f"Start comment pipeline: {(output_path if seed_links else input_path)}",
            )
            _run_comment_pipeline(
                repo_root=repo_root,
                backend_dir=backend_dir,
                input_path=output_path if seed_links else input_path,
                output_path=output_path,
                raw_comments_path=raw_comments_path,
                user_data_path=user_data_path,
                provider=provider,
                limit=limit,
                comment_limit=comment_limit,
                login_wait_seconds=login_wait_seconds,
                resume=resume,
                from_start=from_start,
                force_summary=force_summary,
                headless=headless,
            )
            processed_posts = _count_processed_posts(output_path)
            update_trend_pipeline_run(
                pipeline_run_id,
                stage="import_posts",
                processed_posts=processed_posts,
            )
            append_trend_pipeline_run_log(pipeline_run_id, f"Comment pipeline completed: processed_posts={processed_posts}")
            posts = _load_posts(output_path)

        import_result = import_ugc_posts(posts)
        update_trend_pipeline_run(
            pipeline_run_id,
            stage="trend_discovery",
            imported_posts=import_result["imported_count"],
            updated_posts=import_result["updated_count"],
            payload={"import_result": import_result},
        )
        append_trend_pipeline_run_log(
            pipeline_run_id,
            f"Imported posts: imported={import_result['imported_count']} updated={import_result['updated_count']} total={import_result['total_count']}",
        )

        trend_run = create_trend_run(triggered_by=f"pipeline:{pipeline_run_id}", total_posts=len(posts), status="pending")
        update_trend_pipeline_run(
            pipeline_run_id,
            linked_trend_run_id=trend_run["run_id"],
        )
        append_trend_pipeline_run_log(pipeline_run_id, f"Created trend run: {trend_run['run_id']}")
        execute_trend_run(trend_run["run_id"], min_support, max_trends)
        finished_trend_run = get_trend_run(trend_run["run_id"])
        if not finished_trend_run or finished_trend_run["status"] != "succeeded":
            error_message = finished_trend_run["error_message"] if finished_trend_run else "trend run failed"
            raise RuntimeError(error_message)

        generated_trends = int(finished_trend_run.get("created_trends") or 0)
        update_trend_pipeline_run(
            pipeline_run_id,
            generated_trends=generated_trends,
            payload={
                "import_result": import_result,
                "trend_run": finished_trend_run,
            },
        )
        append_trend_pipeline_run_log(pipeline_run_id, f"Trend discovery completed: generated_trends={generated_trends}")

        converted_results: list[dict[str, Any]] = []
        if auto_convert_to_draft:
            update_trend_pipeline_run(pipeline_run_id, stage="convert_to_draft")
            append_trend_pipeline_run_log(pipeline_run_id, "Start converting trends to drafts")
            for trend in list_trends(limit=max(1, convert_limit), status="promote"):
                converted_results.append(
                    convert_trend_to_draft(
                        trend_id=trend["trend_id"],
                        merchant_id=merchant_id,
                        use_trend_tags=use_trend_tags,
                    )
                )
            update_trend_pipeline_run(
                pipeline_run_id,
                converted_drafts=len(converted_results),
            )
            append_trend_pipeline_run_log(pipeline_run_id, f"Converted drafts: {len(converted_results)}")

        update_trend_pipeline_run(
            pipeline_run_id,
            status="succeeded",
            stage="completed",
            payload={
                "import_result": import_result,
                "trend_run": finished_trend_run,
                "converted_drafts": converted_results,
            },
        )
        append_trend_pipeline_run_log(pipeline_run_id, "Pipeline completed successfully")
    except Exception as exc:
        update_trend_pipeline_run(
            pipeline_run_id,
            status="failed",
            stage="failed",
            error_message=str(exc),
        )
        append_trend_pipeline_run_log(pipeline_run_id, f"Pipeline failed: {exc}")


def _resolve_repo_path(repo_root: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = (repo_root / path).resolve()
    return path


def _count_posts(path: Path) -> int:
    return len(_load_posts(path))


def _count_processed_posts(path: Path) -> int:
    posts = _load_posts(path)
    return _count_completed_posts(posts)


def _count_completed_posts(posts: list[dict[str, Any]]) -> int:
    return sum(
        1
        for post in posts
        if str(post.get("comment_fetch_status") or "") in {"done", "unavailable"}
        and str((post.get("comment_insights") or {}).get("status") or "") in {"done", "unavailable"}
    )


def _load_posts(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    posts = payload.get("posts")
    if not isinstance(posts, list):
        raise RuntimeError("Input JSON must contain a top-level 'posts' array")
    return [post for post in posts if isinstance(post, dict)]


def _run_comment_pipeline(
    *,
    repo_root: Path,
    backend_dir: Path,
    input_path: Path,
    output_path: Path,
    raw_comments_path: Path,
    user_data_path: Path,
    provider: str,
    limit: int | None,
    comment_limit: int,
    login_wait_seconds: int,
    resume: bool,
    from_start: bool,
    force_summary: bool,
    headless: bool,
) -> None:
    node_bin = shutil.which("node")
    if not node_bin:
        raise RuntimeError("node is not installed or not on PATH")
    npm_bin = shutil.which("npm")
    if not npm_bin:
        raise RuntimeError("npm is not installed or not on PATH")
    if not (backend_dir / "node_modules" / "playwright").exists():
        raise RuntimeError("Playwright dependency is not installed. Run `cd backend && npm install && npx playwright install chromium` first.")

    cmd = [
        sys.executable,
        str(backend_dir / "scripts" / "run_xhs_comment_pipeline.py"),
        "--input",
        str(input_path),
        "--output",
        str(output_path),
        "--raw-comments-file",
        str(raw_comments_path),
        "--user-data-dir",
        str(user_data_path),
        "--provider",
        provider,
    ]
    if limit is not None:
        cmd.extend(["--limit", str(limit)])
    cmd.extend([
        "--comment-limit",
        str(comment_limit),
        "--login-wait-seconds",
        str(login_wait_seconds),
    ])
    if resume:
        cmd.append("--resume")
    if from_start:
        cmd.append("--from-start")
    if force_summary:
        cmd.append("--force")
    if headless:
        cmd.append("--headless")

    completed = subprocess.run(
        cmd,
        cwd=repo_root,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        stdout = (completed.stdout or "").strip()
        detail = stderr or stdout or f"comment pipeline exited with code {completed.returncode}"
        raise RuntimeError(detail)


def _build_posts_from_seed_links(
    *,
    repo_root: Path,
    backend_dir: Path,
    seed_links: list[str],
    output_path: Path,
    refresh_ttl_hours: int,
    only_missing: bool,
    force_refresh: bool,
) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as tmp:
        tmp.write("\n".join(seed_links))
        temp_input = Path(tmp.name)
    try:
        cmd = [
            sys.executable,
            str(backend_dir / "scripts" / "build_ugc_json_from_links.py"),
            "--input",
            str(temp_input),
            "--output",
            str(output_path),
            "--refresh-ttl-hours",
            str(refresh_ttl_hours),
        ]
        if only_missing:
            cmd.append("--only-missing")
        if force_refresh:
            cmd.append("--force-refresh")
        completed = subprocess.run(
            cmd,
            cwd=repo_root,
            text=True,
            capture_output=True,
        )
        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            stdout = (completed.stdout or "").strip()
            detail = stderr or stdout or f"build posts exited with code {completed.returncode}"
            raise RuntimeError(detail)
    finally:
        temp_input.unlink(missing_ok=True)
