from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

from app.services.business_db import (
    append_trend_pipeline_run_log,
    create_trend_run,
    get_trend_run,
    import_ugc_posts,
    list_trends,
    update_trend_pipeline_run,
)
from app.services.trend_jobs import execute_trend_run


class PipelineCancelledError(RuntimeError):
    pass


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
    skip_comment_pipeline: bool,
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
    should_cancel: Callable[[], bool] | None = None,
    on_process_start: Callable[[subprocess.Popen[str]], None] | None = None,
    on_process_end: Callable[[], None] | None = None,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    backend_dir = Path(__file__).resolve().parents[2]
    input_path = _resolve_repo_path(repo_root, input_json_path)
    output_path = _resolve_repo_path(repo_root, output_json_path)
    raw_comments_path = _resolve_repo_path(repo_root, raw_comments_file)
    user_data_path = _resolve_repo_path(repo_root, user_data_dir)

    try:
        _raise_if_cancelled(should_cancel)
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
                raw_posts_path = _derive_raw_posts_path(input_path, output_path)
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
                    output_path=raw_posts_path,
                    refresh_ttl_hours=refresh_ttl_hours,
                    only_missing=only_missing,
                    force_refresh=force_refresh,
                    should_cancel=should_cancel,
                    on_process_start=on_process_start,
                    on_process_end=on_process_end,
                )
                _raise_if_cancelled(should_cancel)
                batch_raw_posts = _select_posts_by_source_urls(_load_posts(raw_posts_path), normalized_links)
                batch_post_count = len(batch_raw_posts)
                update_trend_pipeline_run(
                    pipeline_run_id,
                    status="running",
                    stage="classify_posts",
                    total_posts=batch_post_count,
                    error_message="",
                    payload={"source_mode": "seed_links"},
                )
                classify_pending_count = _count_posts_needing_classification(raw_posts_path, output_path, normalized_links)
                update_trend_pipeline_run(
                    pipeline_run_id,
                    payload={"classify_pending_count": classify_pending_count},
                )
                append_trend_pipeline_run_log(
                    pipeline_run_id,
                    f"Classify raw posts {raw_posts_path} into clean view {output_path} (pending={classify_pending_count})",
                )
                classify_result = _run_classify_pipeline(
                    repo_root=repo_root,
                    backend_dir=backend_dir,
                    input_path=raw_posts_path,
                    output_path=output_path,
                    provider=provider,
                    should_cancel=should_cancel,
                    on_process_start=on_process_start,
                    on_process_end=on_process_end,
                )
                _raise_if_cancelled(should_cancel)
                update_trend_pipeline_run(
                    pipeline_run_id,
                    payload={
                        "classify_pending_count": classify_pending_count,
                        "classify_result": classify_result,
                    },
                )
                append_trend_pipeline_run_log(
                    pipeline_run_id,
                    "Classify pipeline completed: "
                    f"processed={classify_result['processed']} "
                    f"skipped={classify_result['skipped']} "
                    f"provider={classify_result['provider']}",
                )
                batch_posts = _select_posts_by_source_urls(_load_posts(output_path), normalized_links)
            else:
                batch_posts = []

            working_path = output_path if (seed_links or output_path.exists()) else input_path
            total_posts = len(batch_posts) if seed_links else _count_posts(working_path)
            if skip_comment_pipeline:
                posts = batch_posts if seed_links else _load_posts(working_path)
                processed_posts = _count_completed_posts(posts)
                update_trend_pipeline_run(
                    pipeline_run_id,
                    status="running",
                    stage="import_posts",
                    total_posts=total_posts,
                    processed_posts=processed_posts,
                    error_message="",
                    payload={"source_mode": "clean_rerun" if not seed_links else "seed_links"},
                )
                append_trend_pipeline_run_log(
                    pipeline_run_id,
                    f"Skip comment pipeline and reuse cleaned posts: {working_path}",
                )
            else:
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
                    f"Start comment pipeline: {working_path}",
                )
                _run_comment_pipeline(
                    repo_root=repo_root,
                    backend_dir=backend_dir,
                    input_path=working_path,
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
                    post_ids=[str(post.get("post_id") or "") for post in batch_posts] if seed_links else None,
                    should_cancel=should_cancel,
                    on_process_start=on_process_start,
                    on_process_end=on_process_end,
                )
                _raise_if_cancelled(should_cancel)
                posts = _select_posts_by_source_urls(_load_posts(output_path), normalized_links) if seed_links else _load_posts(output_path)
                processed_posts = _count_completed_posts(posts)
                update_trend_pipeline_run(
                    pipeline_run_id,
                    stage="import_posts",
                    total_posts=len(posts),
                    processed_posts=processed_posts,
                )
                append_trend_pipeline_run_log(pipeline_run_id, f"Comment pipeline completed: processed_posts={processed_posts}")

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
        _raise_if_cancelled(should_cancel)
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

        # 趋势已通过 trend_jobs 自动进入爆款推送队列（待上架），无需再转草稿
        update_trend_pipeline_run(
            pipeline_run_id,
            status="succeeded",
            stage="completed",
            payload={
                "import_result": import_result,
                "trend_run": finished_trend_run,
            },
        )
        append_trend_pipeline_run_log(pipeline_run_id, "Pipeline completed successfully")
    except PipelineCancelledError as exc:
        update_trend_pipeline_run(
            pipeline_run_id,
            status="cancelled",
            stage="cancelled",
            error_message=str(exc),
            payload={"cancelled": True},
        )
        append_trend_pipeline_run_log(pipeline_run_id, f"Pipeline cancelled: {exc}")
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


def _derive_raw_posts_path(input_path: Path, output_path: Path) -> Path:
    for candidate in (input_path, output_path):
        name = candidate.name
        if "_clean" in name:
            return candidate.with_name(name.replace("_clean", "", 1))
    return output_path


def _count_posts(path: Path) -> int:
    return len(_load_posts(path))


def _count_processed_posts(path: Path) -> int:
    posts = _load_posts(path)
    return _count_completed_posts(posts)


def _count_posts_needing_classification(raw_path: Path, existing_clean_path: Path, source_urls: list[str] | None = None) -> int:
    raw_posts = _load_posts(raw_path)
    if source_urls:
        raw_posts = _select_posts_by_source_urls(raw_posts, source_urls)
    existing_posts = []
    if existing_clean_path.exists():
        try:
            existing_posts = _load_posts(existing_clean_path)
        except Exception:
            existing_posts = []
    existing_by_post_id = {
        str(post.get("post_id") or "").strip(): post
        for post in existing_posts
        if isinstance(post, dict) and str(post.get("post_id") or "").strip()
    }
    existing_by_source_url = {
        str(post.get("source_url") or "").strip(): post
        for post in existing_posts
        if isinstance(post, dict) and str(post.get("source_url") or "").strip()
    }
    pending = 0
    for post in raw_posts:
        if not isinstance(post, dict):
            continue
        post_id = str(post.get("post_id") or "").strip()
        source_url = str(post.get("source_url") or "").strip()
        existing = existing_by_post_id.get(post_id) or existing_by_source_url.get(source_url)
        if str((existing or {}).get("classification_status") or "") != "done":
            pending += 1
    return pending


def _select_posts_by_source_urls(posts: list[dict[str, Any]], source_urls: list[str]) -> list[dict[str, Any]]:
    wanted = {str(item).strip() for item in source_urls if str(item).strip()}
    if not wanted:
        return posts
    selected: list[dict[str, Any]] = []
    for post in posts:
        if not isinstance(post, dict):
            continue
        if str(post.get("source_url") or "").strip() in wanted:
            selected.append(post)
    return selected


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
    post_ids: list[str] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    on_process_start: Callable[[subprocess.Popen[str]], None] | None = None,
    on_process_end: Callable[[], None] | None = None,
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
    for post_id in post_ids or []:
        if post_id:
            cmd.extend(["--post-id", post_id])

    completed = _run_subprocess_with_cancellation(
        cmd,
        cwd=repo_root,
        should_cancel=should_cancel,
        on_process_start=on_process_start,
        on_process_end=on_process_end,
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
    should_cancel: Callable[[], bool] | None = None,
    on_process_start: Callable[[subprocess.Popen[str]], None] | None = None,
    on_process_end: Callable[[], None] | None = None,
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
        completed = _run_subprocess_with_cancellation(
            cmd,
            cwd=repo_root,
            should_cancel=should_cancel,
            on_process_start=on_process_start,
            on_process_end=on_process_end,
        )
        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            stdout = (completed.stdout or "").strip()
            detail = stderr or stdout or f"build posts exited with code {completed.returncode}"
            raise RuntimeError(detail)
    finally:
        temp_input.unlink(missing_ok=True)


def _run_classify_pipeline(
    *,
    repo_root: Path,
    backend_dir: Path,
    input_path: Path,
    output_path: Path,
    provider: str,
    should_cancel: Callable[[], bool] | None = None,
    on_process_start: Callable[[subprocess.Popen[str]], None] | None = None,
    on_process_end: Callable[[], None] | None = None,
) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(backend_dir / "scripts" / "classify_ugc_posts.py"),
        "--input",
        str(input_path),
        "--output",
        str(output_path),
        "--provider",
        provider,
    ]
    completed = _run_subprocess_with_cancellation(
        cmd,
        cwd=repo_root,
        should_cancel=should_cancel,
        on_process_start=on_process_start,
        on_process_end=on_process_end,
    )
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        stdout = (completed.stdout or "").strip()
        detail = stderr or stdout or f"classify posts exited with code {completed.returncode}"
        raise RuntimeError(detail)
    return _parse_classify_stdout(completed.stdout or "", provider)


def _raise_if_cancelled(should_cancel: Callable[[], bool] | None) -> None:
    if should_cancel and should_cancel():
        raise PipelineCancelledError("任务已取消")


def _run_subprocess_with_cancellation(
    cmd: list[str],
    *,
    cwd: Path,
    should_cancel: Callable[[], bool] | None = None,
    on_process_start: Callable[[subprocess.Popen[str]], None] | None = None,
    on_process_end: Callable[[], None] | None = None,
) -> subprocess.CompletedProcess[str]:
    _raise_if_cancelled(should_cancel)
    process = subprocess.Popen(
        cmd,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if on_process_start:
        on_process_start(process)
    try:
        while True:
            if should_cancel and should_cancel():
                try:
                    process.terminate()
                    process.wait(timeout=5)
                except Exception:
                    try:
                        process.kill()
                    except Exception:
                        pass
                raise PipelineCancelledError("任务已取消")
            return_code = process.poll()
            if return_code is not None:
                stdout, stderr = process.communicate()
                return subprocess.CompletedProcess(cmd, return_code, stdout, stderr)
            time.sleep(0.4)
    finally:
        if on_process_end:
            on_process_end()


def _parse_classify_stdout(stdout: str, provider: str) -> dict[str, Any]:
    processed = 0
    skipped = 0
    actual_provider = provider
    for line in stdout.splitlines():
        text = line.strip()
        if not text:
            continue
        if text.startswith("processed="):
            for chunk in text.split():
                if chunk.startswith("processed="):
                    try:
                        processed = int(chunk.split("=", 1)[1])
                    except ValueError:
                        processed = 0
                elif chunk.startswith("skipped="):
                    try:
                        skipped = int(chunk.split("=", 1)[1])
                    except ValueError:
                        skipped = 0
                elif chunk.startswith("provider="):
                    actual_provider = chunk.split("=", 1)[1] or actual_provider
    return {
        "processed": processed,
        "skipped": skipped,
        "provider": actual_provider,
    }
