#!/usr/bin/env python3
"""Offline preprocess style nail regions with Qwen 2.5 VL.

Usage:
    cd backend
    python scripts/preprocess_style_nail_regions.py
    python scripts/preprocess_style_nail_regions.py --limit 10
    python scripts/preprocess_style_nail_regions.py --style-id style-seed-001 --force
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.services.business_db import list_styles
from app.services.image_storage import storage_root
from app.services.multimodal_client import (
    MultimodalModelError,
    analyze_image_json_with_qwen_vl,
    is_qwen_vl_enabled,
)


SYSTEM_PROMPT = """你是一个只输出严格 JSON 的视觉定位器。

任务目标：
识别一张美甲款式图里从左到右 5 根手指的指甲区域。

输出要求：
1. 只能输出一个 JSON 对象，不能输出任何解释、Markdown、代码块或额外文字。
2. 顶层 key 必须且只能是字符串 "1" "2" "3" "4" "5"。
3. 每个 key 的 value 必须是长度为 4 的数组，表示该指甲区域的四个角点。
4. 每个角点必须是 [x, y] 两个数字。
5. x 和 y 都必须是 0 到 1 之间的归一化小数。
6. 四个角点必须按照顺时针顺序排列，并尽量贴合指甲本身的倾斜角度。
7. 如果某根手指边界不清晰，也必须基于可见区域给出最合理的四边形估计，不能缺失 key。
8. 不要输出 null，不要输出字符串坐标，不要输出整数序号之外的字段。
"""


USER_PROMPT_TEMPLATE = """这是一张美甲款式图，图中有五根手指的指甲。

请从左到右将手指编号为 1-5，并为每根手指输出能贴合指甲倾斜角度的四个角点坐标。

坐标格式：
{{
  "1": [[x1, y1], [x2, y2], [x3, y3], [x4, y4]],
  "2": [[...], [...], [...], [...]],
  "3": [[...], [...], [...], [...]],
  "4": [[...], [...], [...], [...]],
  "5": [[...], [...], [...], [...]]
}}

补充要求：
- 四个点按顺时针顺序排列。
- 坐标必须是 0 到 1 的归一化数值。
- 只输出 JSON。

当前款式信息：
- style_id: {style_id}
- style_name: {style_name}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Preprocess nail corner regions for style images with Qwen VL")
    parser.add_argument("--limit", type=int, default=None, help="Only process first N styles")
    parser.add_argument("--style-id", action="append", default=[], help="Only process specific style_id, can repeat")
    parser.add_argument("--force", action="store_true", help="Re-run even if output file already exists")
    parser.add_argument(
        "--status",
        default=None,
        help="Optional style status filter passed to list_styles, e.g. active / draft",
    )
    args = parser.parse_args()

    if not is_qwen_vl_enabled():
        raise SystemExit("QWEN_API_KEY is not configured or MODEL_REAL_ENABLED is false")

    styles = list_styles(limit=5000, status=args.status)
    if args.style_id:
        wanted = set(args.style_id)
        styles = [item for item in styles if str(item.get("style_id") or "") in wanted]

    if args.limit is not None:
        styles = styles[: args.limit]

    if not styles:
        print("No styles to process.")
        return

    output_dir = _output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    failure_dir = output_dir / "_failures"
    failure_dir.mkdir(parents=True, exist_ok=True)

    processed = 0
    skipped = 0
    failed = 0
    manifest_items: list[dict[str, Any]] = []

    for style in styles:
        style_id = str(style.get("style_id") or "").strip()
        style_name = str(style.get("style_name") or "").strip() or style_id
        image_url = _style_image_url(style)
        if not style_id or not image_url:
            failed += 1
            print(f"[failed] missing style_id or image_url: {style_name}")
            continue

        output_path = output_dir / f"{style_id}.json"
        if output_path.exists() and not args.force:
            skipped += 1
            manifest_items.append(_load_manifest_item(output_path))
            print(f"[skip] {style_id}")
            continue

        raw = None
        try:
            raw = analyze_image_json_with_qwen_vl(
                image_url=image_url,
                system_prompt=SYSTEM_PROMPT,
                user_prompt=USER_PROMPT_TEMPLATE.format(style_id=style_id, style_name=style_name),
            )
            nail_regions = _normalize_nail_regions(raw)
        except (MultimodalModelError, ValueError) as exc:
            failed += 1
            _write_failure_payload(
                failure_dir / f"{style_id}.json",
                style_id=style_id,
                style_name=style_name,
                image_url=image_url,
                raw=raw,
                error=str(exc),
            )
            print(f"[failed] {style_id}: {exc}")
            continue

        payload = {
            "style_id": style_id,
            "style_name": style_name,
            "image_url": image_url,
            "analysis_mode": get_settings().qwen_vl_model_name,
            "prompt_version": "nail-region-v1",
            "processed_at": _now_iso(),
            "nail_regions": nail_regions,
            "model_output": raw,
        }
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest_items.append(_manifest_item_from_payload(payload, output_path))
        processed += 1
        print(f"[done] {style_id}")

    _write_manifest(output_dir / "manifest.json", manifest_items)
    print(
        f"written: {output_dir}\n"
        f"processed={processed} skipped={skipped} failed={failed} model={get_settings().qwen_vl_model_name}"
    )


def _style_image_url(style: dict[str, Any]) -> str:
    return str(
        style.get("enhanced_style_image_url")
        or style.get("original_style_image_url")
        or style.get("image_url")
        or ""
    ).strip()


def _output_dir() -> Path:
    return storage_root() / "tune_references" / "style_nail_regions"


def _normalize_nail_regions(data: dict[str, Any]) -> dict[str, list[list[float]]]:
    if not isinstance(data, dict):
        raise ValueError("model output is not a JSON object")

    finger_map = _extract_finger_map(data)
    normalized: dict[str, list[list[float]]] = {}
    expected = {"1", "2", "3", "4", "5"}
    if set(finger_map.keys()) != expected:
        raise ValueError(f"model output keys must be exactly {sorted(expected)}")

    for finger in ("1", "2", "3", "4", "5"):
        points = _extract_points(finger_map.get(finger), finger=finger)

        normalized_points: list[list[float]] = []
        for idx, point in enumerate(points, start=1):
            x, y = _extract_xy(point, finger=finger, point_idx=idx)
            normalized_points.append([x, y])
        normalized[finger] = normalized_points
    return normalized


def _extract_finger_map(data: dict[str, Any]) -> dict[str, Any]:
    direct = {str(key): value for key, value in data.items()}
    if {"1", "2", "3", "4", "5"}.issubset(direct.keys()):
        return {finger: direct[finger] for finger in ("1", "2", "3", "4", "5")}

    for candidate_key in ("result", "data", "nails", "nail_regions", "regions", "output"):
        candidate = data.get(candidate_key)
        if isinstance(candidate, dict):
            nested = {str(key): value for key, value in candidate.items()}
            if {"1", "2", "3", "4", "5"}.issubset(nested.keys()):
                return {finger: nested[finger] for finger in ("1", "2", "3", "4", "5")}

    raise ValueError("model output does not contain finger keys 1-5")


def _extract_points(value: Any, *, finger: str) -> list[Any]:
    points = value
    if isinstance(points, dict):
        for key in ("points", "corners", "polygon", "coords", "coordinates", "vertices", "region"):
            candidate = points.get(key)
            if isinstance(candidate, list):
                points = candidate
                break
        else:
            indexed: list[Any] = []
            for key in ("1", "2", "3", "4", "p1", "p2", "p3", "p4", "top_left", "top_right", "bottom_right", "bottom_left"):
                if key in points:
                    indexed.append(points[key])
            if len(indexed) == 4:
                points = indexed

    if (
        isinstance(points, list)
        and len(points) == 1
        and isinstance(points[0], list)
        and len(points[0]) == 8
        and all(not isinstance(item, (list, tuple, dict)) for item in points[0])
    ):
        points = points[0]

    if isinstance(points, list) and len(points) == 5 and points[0] == points[-1]:
        points = points[:4]

    if isinstance(points, list) and len(points) == 8 and all(not isinstance(item, (list, tuple, dict)) for item in points):
        points = [[points[0], points[1]], [points[2], points[3]], [points[4], points[5]], [points[6], points[7]]]

    if not isinstance(points, list) or len(points) != 4:
        raise ValueError(f"finger {finger} must contain exactly 4 corner points")
    return points


def _extract_xy(point: Any, *, finger: str, point_idx: int) -> tuple[float, float]:
    if isinstance(point, (list, tuple)) and len(point) == 2:
        return (
            _as_coord(point[0], finger=finger, point_idx=point_idx, axis="x"),
            _as_coord(point[1], finger=finger, point_idx=point_idx, axis="y"),
        )

    if isinstance(point, dict):
        if "x" in point and "y" in point:
            return (
                _as_coord(point["x"], finger=finger, point_idx=point_idx, axis="x"),
                _as_coord(point["y"], finger=finger, point_idx=point_idx, axis="y"),
            )
        if "X" in point and "Y" in point:
            return (
                _as_coord(point["X"], finger=finger, point_idx=point_idx, axis="x"),
                _as_coord(point["Y"], finger=finger, point_idx=point_idx, axis="y"),
            )

    raise ValueError(f"finger {finger} point {point_idx} must be [x, y]")


def _as_coord(value: Any, *, finger: str, point_idx: int, axis: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"finger {finger} point {point_idx} axis {axis} is not numeric") from exc
    if number < 0 or number > 1:
        raise ValueError(f"finger {finger} point {point_idx} axis {axis} out of range [0,1]: {number}")
    return round(number, 6)


def _load_manifest_item(output_path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "style_id": output_path.stem,
            "file": output_path.name,
            "status": "existing_invalid",
        }
    return _manifest_item_from_payload(payload, output_path)


def _write_failure_payload(
    path: Path,
    *,
    style_id: str,
    style_name: str,
    image_url: str,
    raw: Any,
    error: str,
) -> None:
    payload = {
        "style_id": style_id,
        "style_name": style_name,
        "image_url": image_url,
        "failed_at": _now_iso(),
        "error": error,
        "model_output": raw,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _manifest_item_from_payload(payload: dict[str, Any], output_path: Path) -> dict[str, Any]:
    return {
        "style_id": payload.get("style_id"),
        "style_name": payload.get("style_name"),
        "image_url": payload.get("image_url"),
        "analysis_mode": payload.get("analysis_mode"),
        "prompt_version": payload.get("prompt_version"),
        "processed_at": payload.get("processed_at"),
        "file": output_path.name,
        "status": "done",
    }


def _write_manifest(path: Path, items: list[dict[str, Any]]) -> None:
    payload = {
        "generated_at": _now_iso(),
        "count": len(items),
        "items": items,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    main()
