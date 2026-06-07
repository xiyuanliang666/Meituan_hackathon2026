from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.services.image_storage import storage_root
from app.services.multimodal_client import (
    MultimodalModelError,
    analyze_image_json_with_nail_region_vlm,
    is_nail_region_vlm_enabled,
)

SYSTEM_PROMPT = """你是一个只输出严格 JSON 的视觉定位器。

任务目标：
识别一张裸手手模图里从左到右 5 根手指的指甲区域。

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


def build_hand_nail_region_user_prompt(hand_id: str, hand_label: str) -> str:
    return """这是一张裸手手模图，图中有五根手指的指甲。

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

当前手模信息：
- hand_id: {hand_id}
- hand_label: {hand_label}
""".format(hand_id=hand_id, hand_label=hand_label)


def hand_nail_regions_output_dir() -> Path:
    return storage_root() / "tune_references" / "hand_nail_regions"


def hand_nail_regions_output_path(hand_id: str) -> Path:
    return hand_nail_regions_output_dir() / f"{hand_id}.json"


def hand_nail_regions_failure_path(hand_id: str) -> Path:
    return hand_nail_regions_output_dir() / "_failures" / f"{hand_id}.json"


def get_hand_nail_region_status(hand_id: str) -> dict[str, Any]:
    success_path = hand_nail_regions_output_path(hand_id)
    failure_path = hand_nail_regions_failure_path(hand_id)

    if success_path.exists():
        try:
            payload = json.loads(success_path.read_text(encoding="utf-8"))
            regions = payload.get("nail_regions")
            if isinstance(regions, dict) and set(regions.keys()) == {"1", "2", "3", "4", "5"}:
                return {
                    "status": "done",
                    "json_path": str(success_path),
                    "error": "",
                    "payload": payload,
                }
        except (OSError, json.JSONDecodeError):
            pass

    if failure_path.exists():
        try:
            payload = json.loads(failure_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        return {
            "status": "failed",
            "json_path": str(failure_path),
            "error": str(payload.get("error") or "hand nail region extraction failed"),
            "payload": payload,
        }

    return {"status": "pending", "json_path": "", "error": "", "payload": None}


def get_hand_nail_region_payload(hand_id: str) -> dict[str, Any] | None:
    status = get_hand_nail_region_status(hand_id)
    payload = status.get("payload")
    return payload if isinstance(payload, dict) else None


def extract_and_store_hand_nail_regions(hand_id: str, image_url: str, hand_label: str = "") -> dict[str, Any]:
    output_dir = hand_nail_regions_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "_failures").mkdir(parents=True, exist_ok=True)

    output_path = hand_nail_regions_output_path(hand_id)
    failure_path = hand_nail_regions_failure_path(hand_id)
    raw: Any = None

    if not is_nail_region_vlm_enabled():
        error = "NAIL_REGION_VLM_API_KEY is not configured or MODEL_REAL_ENABLED is false"
        _write_failure_payload(failure_path, hand_id=hand_id, hand_label=hand_label, image_url=image_url, raw=raw, error=error)
        if output_path.exists():
            output_path.unlink(missing_ok=True)
        return {"status": "failed", "json_path": str(failure_path), "error": error}

    try:
        raw = analyze_image_json_with_nail_region_vlm(
            image_url=image_url,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=build_hand_nail_region_user_prompt(hand_id=hand_id, hand_label=hand_label or hand_id),
        )
        nail_regions = _normalize_nail_regions(raw)
    except (MultimodalModelError, ValueError) as exc:
        error = str(exc)
        _write_failure_payload(failure_path, hand_id=hand_id, hand_label=hand_label, image_url=image_url, raw=raw, error=error)
        if output_path.exists():
            output_path.unlink(missing_ok=True)
        return {"status": "failed", "json_path": str(failure_path), "error": error}

    payload = {
        "hand_id": hand_id,
        "hand_label": hand_label or hand_id,
        "image_url": image_url,
        "analysis_mode": get_settings().nail_region_vlm_model_name,
        "prompt_version": "hand-nail-region-v1",
        "processed_at": _now_iso(),
        "nail_regions": nail_regions,
        "model_output": raw,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if failure_path.exists():
        failure_path.unlink(missing_ok=True)
    return {"status": "done", "json_path": str(output_path), "error": "", "payload": payload}


def _write_failure_payload(
    path: Path,
    *,
    hand_id: str,
    hand_label: str,
    image_url: str,
    raw: Any,
    error: str,
) -> None:
    payload = {
        "hand_id": hand_id,
        "hand_label": hand_label or hand_id,
        "image_url": image_url,
        "failed_at": _now_iso(),
        "error": error,
        "model_output": raw,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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
        normalized[finger] = [[_extract_xy(point, finger=finger, point_idx=idx)[0], _extract_xy(point, finger=finger, point_idx=idx)[1]] for idx, point in enumerate(points, start=1)]
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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
