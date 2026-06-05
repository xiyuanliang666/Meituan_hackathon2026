from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.services.business_db import get_trend, update_trend_representative_image


def resolve_trend_cover(trend_id: str) -> dict[str, Any]:
    trend = get_trend(trend_id)
    if not trend:
        raise ValueError("trend not found")

    current = str(trend.get("representative_image_url") or "").strip()
    if current and "/static/" in current:
        return {"trend_id": trend_id, "image_url": current, "resolved": False}

    supporting_posts = trend.get("supporting_posts") or []
    representative_post = supporting_posts[0] if supporting_posts and isinstance(supporting_posts[0], dict) else {}
    source_url = str(representative_post.get("source_url") or "").strip()
    post_id = str(representative_post.get("post_id") or trend_id).strip()
    if not source_url:
        raise ValueError("representative source url not found")

    repo_root = Path(__file__).resolve().parents[3]
    output_path = repo_root / "backend" / "storage" / "trend_post_captures" / f"{post_id}.jpg"
    script_path = repo_root / "backend" / "scripts" / "capture_xhs_post_cover.mjs"
    user_data_dir = repo_root / "backend" / ".playwright-xhs-profile"

    completed = subprocess.run(
        [
            "node",
            str(script_path),
            "--url",
            source_url,
            "--post-id",
            post_id,
            "--output-path",
            str(output_path),
            "--user-data-dir",
            str(user_data_dir),
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(completed.stdout.strip() or "{}")
    image_url = str(payload.get("image_url") or "").strip()
    if not image_url:
        raise ValueError("failed to generate trend cover")

    updated = update_trend_representative_image(trend_id, image_url)
    return {
        "trend_id": trend_id,
        "image_url": image_url,
        "resolved": True,
        "trend": updated or trend,
    }
