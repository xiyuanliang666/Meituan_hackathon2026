"""Taxonomy v2 persistence, prompt building, validation, and user submissions."""

from __future__ import annotations

import json
import sqlite3
from typing import Any
from uuid import uuid4

from app.data.nail_taxonomy_v2_seed import (
    ARRAY_FIELD_KEYS,
    ENUM_FIELD_KEYS,
    STYLE_TAG_FIELD_KEYS,
    TAXONOMY_V2_FIELDS,
    TAXONOMY_V2_OPTIONS,
)
from app.services.business_db import connect_db, _now


def ensure_taxonomy_seeded(conn: sqlite3.Connection) -> None:
    _ensure_tables(conn)
    count = conn.execute("SELECT COUNT(*) FROM taxonomy_fields").fetchone()[0]
    if count > 0:
        return
    now = _now()
    for field in TAXONOMY_V2_FIELDS:
        conn.execute(
            """
            INSERT INTO taxonomy_fields
            (field_key, label_cn, value_type, dimension, sort_order)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                field["field_key"],
                field["label_cn"],
                field["value_type"],
                field["dimension"],
                field["sort_order"],
            ),
        )
    for field_key, values in TAXONOMY_V2_OPTIONS.items():
        for value in values:
            conn.execute(
                """
                INSERT INTO taxonomy_options
                (option_id, field_key, value, is_approved, source, created_at)
                VALUES (?, ?, ?, 1, 'seed_v2', ?)
                """,
                (f"opt-{uuid4().hex[:12]}", field_key, value, now),
            )


def list_taxonomy(include_unapproved: bool = False) -> dict[str, Any]:
    with connect_db() as conn:
        _ensure_tables(conn)
        ensure_taxonomy_seeded(conn)
        fields = [
            dict(row)
            for row in conn.execute(
                """
                SELECT field_key, label_cn, value_type, dimension, sort_order
                FROM taxonomy_fields
                ORDER BY sort_order
                """
            ).fetchall()
        ]
        approved_clause = "" if include_unapproved else "AND is_approved = 1"
        options_rows = conn.execute(
            f"""
            SELECT field_key, value, is_approved, source
            FROM taxonomy_options
            WHERE 1=1 {approved_clause}
            ORDER BY field_key, value
            """
        ).fetchall()
        options_by_field: dict[str, list[dict[str, Any]]] = {key: [] for key in STYLE_TAG_FIELD_KEYS}
        for row in options_rows:
            options_by_field.setdefault(row["field_key"], []).append(
                {
                    "value": row["value"],
                    "is_approved": bool(row["is_approved"]),
                    "source": row["source"],
                }
            )
        for field in fields:
            field["options"] = options_by_field.get(field["field_key"], [])
        return {"fields": fields, "version": "v2"}


def get_approved_values_map(conn: sqlite3.Connection | None = None) -> dict[str, set[str]]:
    if conn is None:
        with connect_db() as owned:
            _ensure_tables(owned)
            ensure_taxonomy_seeded(owned)
            return get_approved_values_map(owned)

    rows = conn.execute(
        """
        SELECT field_key, value
        FROM taxonomy_options
        WHERE is_approved = 1
        """
    ).fetchall()
    result: dict[str, set[str]] = {key: set() for key in STYLE_TAG_FIELD_KEYS}
    for row in rows:
        result.setdefault(row["field_key"], set()).add(row["value"])
    return result


def get_all_approved_tag_values() -> set[str]:
    with connect_db() as conn:
        _ensure_tables(conn)
        ensure_taxonomy_seeded(conn)
        rows = conn.execute(
            "SELECT value FROM taxonomy_options WHERE is_approved = 1"
        ).fetchall()
    return {row["value"] for row in rows}


def get_popular_style_tag_values(limit: int = 6) -> list[str]:
    with connect_db() as conn:
        _ensure_tables(conn)
        rows = conn.execute(
            """
            SELECT tag_value, COUNT(*) AS cnt
            FROM style_tags
            GROUP BY tag_value
            ORDER BY cnt DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    if rows:
        return [row["tag_value"] for row in rows]
    approved = get_all_approved_tag_values()
    return sorted(approved)[:limit]


def build_tagging_prompt() -> tuple[str, str]:
    """Return (system_prompt, user_prompt_template_suffix)."""
    with connect_db() as conn:
        _ensure_tables(conn)
        ensure_taxonomy_seeded(conn)
        approved = get_approved_values_map(conn)

    value_domain_lines: list[str] = []
    for field in TAXONOMY_V2_FIELDS:
        key = str(field["field_key"])
        label = str(field["label_cn"])
        vtype = str(field["value_type"])
        values = sorted(approved.get(key, set()))
        if vtype == "array":
            value_domain_lines.append(f"- {key}（{label}，数组，可多选）: {', '.join(values)}")
        else:
            value_domain_lines.append(f"- {key}（{label}，枚举，单选）: {', '.join(values)}")

    system_prompt = (
        "你是美甲款式图结构化打标助手。只输出合法 JSON，不要输出 Markdown。"
        "必须对全部 12 个字段完成打标；数组字段只能从值域中选一个或多个；"
        "枚举字段只能选一个值；无法判断时数组填 []，枚举填 unknown。"
        "禁止自造值域外标签；若确有合适但值域没有的新词，写入 candidate_tags，格式为「字段名: 建议值」。"
        "字段名使用英文，字段值使用中文。"
    )
    user_prompt = (
        "请分析这张美甲款式图，输出 JSON，包含以下字段：\n"
        + "\n".join(value_domain_lines)
        + "\n- candidate_tags（数组，无溢出时填 []）\n"
        "打标原则：season_tags 若选「四季通用」则不再叠加其他季节；"
        "nail_decoration 若选「无装饰」则不再叠加其他装饰；"
        "skin_tone_suitability 若选「全肤色通用」则不再叠加其他肤色。"
    )
    return system_prompt, user_prompt


def validate_style_tags(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize model/user tag payload against approved taxonomy options."""
    with connect_db() as conn:
        _ensure_tables(conn)
        ensure_taxonomy_seeded(conn)
        approved = get_approved_values_map(conn)

    normalized: dict[str, Any] = {}
    for key in ARRAY_FIELD_KEYS:
        values = raw.get(key, [])
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, list):
            values = []
        allowed = approved.get(key, set())
        normalized[key] = [str(v).strip() for v in values if str(v).strip() in allowed]

    for key in ENUM_FIELD_KEYS:
        value = raw.get(key, "unknown")
        allowed = approved.get(key, set())
        text = str(value).strip() if value is not None else "unknown"
        normalized[key] = text if text in allowed else "unknown"

    candidate = raw.get("candidate_tags", [])
    if not isinstance(candidate, list):
        candidate = []
    normalized["candidate_tags"] = [str(item).strip() for item in candidate if str(item).strip()]
    return normalized


def style_tags_to_storage_dict(tags: dict[str, Any]) -> dict[str, list[str]]:
    """Convert validated tags to style_tags table rows (tag_type -> values)."""
    storage: dict[str, list[str]] = {}
    for key in ARRAY_FIELD_KEYS:
        values = tags.get(key, [])
        if values:
            storage[key] = list(values)
    for key in ENUM_FIELD_KEYS:
        value = tags.get(key, "unknown")
        if value and value != "unknown":
            storage[key] = [str(value)]
    return storage


def storage_dict_to_style_tags(storage: dict[str, list[str]]) -> dict[str, Any]:
    result: dict[str, Any] = {key: [] for key in ARRAY_FIELD_KEYS}
    for key in ENUM_FIELD_KEYS:
        result[key] = "unknown"
    for tag_type, values in storage.items():
        if tag_type in ARRAY_FIELD_KEYS:
            result[tag_type] = list(values)
        elif tag_type in ENUM_FIELD_KEYS and values:
            result[tag_type] = values[0]
    result["candidate_tags"] = storage.get("candidate_tags", [])
    return result


def submit_taxonomy_value(
    field_key: str,
    proposed_value: str,
    submitted_by: str | None = None,
) -> dict[str, Any]:
    proposed_value = proposed_value.strip()
    if not proposed_value:
        raise ValueError("proposed_value is required")
    if field_key not in STYLE_TAG_FIELD_KEYS:
        raise ValueError(f"unknown field_key: {field_key}")

    with connect_db() as conn:
        _ensure_tables(conn)
        ensure_taxonomy_seeded(conn)
        existing = conn.execute(
            """
            SELECT 1 FROM taxonomy_options
            WHERE field_key = ? AND value = ? AND is_approved = 1
            """,
            (field_key, proposed_value),
        ).fetchone()
        if existing:
            raise ValueError("该标签已在正式值域中")

        pending = conn.execute(
            """
            SELECT submission_id FROM taxonomy_submissions
            WHERE field_key = ? AND proposed_value = ? AND is_approved = 0
            """,
            (field_key, proposed_value),
        ).fetchone()
        if pending:
            return {
                "submission_id": pending["submission_id"],
                "field_key": field_key,
                "proposed_value": proposed_value,
                "is_approved": False,
                "status": "already_pending",
            }

        submission_id = f"sub-{uuid4().hex[:12]}"
        created_at = _now()
        conn.execute(
            """
            INSERT INTO taxonomy_submissions
            (submission_id, field_key, proposed_value, submitted_by, is_approved, created_at)
            VALUES (?, ?, ?, ?, 0, ?)
            """,
            (submission_id, field_key, proposed_value, submitted_by, created_at),
        )
        conn.execute(
            """
            INSERT INTO taxonomy_options
            (option_id, field_key, value, is_approved, source, created_at)
            VALUES (?, ?, ?, 0, 'user_submission', ?)
            """,
            (f"opt-{uuid4().hex[:12]}", field_key, proposed_value, created_at),
        )
    return {
        "submission_id": submission_id,
        "field_key": field_key,
        "proposed_value": proposed_value,
        "is_approved": False,
        "status": "pending",
    }


def list_taxonomy_submissions(approved: bool | None = None) -> list[dict[str, Any]]:
    with connect_db() as conn:
        _ensure_tables(conn)
        query = """
            SELECT submission_id, field_key, proposed_value, submitted_by,
                   is_approved, created_at
            FROM taxonomy_submissions
        """
        params: tuple[Any, ...] = ()
        if approved is not None:
            query += " WHERE is_approved = ?"
            params = (1 if approved else 0,)
        query += " ORDER BY created_at DESC"
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def set_submission_approved(submission_id: str, is_approved: bool) -> dict[str, Any]:
    with connect_db() as conn:
        row = conn.execute(
            """
            SELECT submission_id, field_key, proposed_value
            FROM taxonomy_submissions
            WHERE submission_id = ?
            """,
            (submission_id,),
        ).fetchone()
        if not row:
            raise ValueError("submission not found")
        flag = 1 if is_approved else 0
        conn.execute(
            "UPDATE taxonomy_submissions SET is_approved = ? WHERE submission_id = ?",
            (flag, submission_id),
        )
        conn.execute(
            """
            UPDATE taxonomy_options
            SET is_approved = ?
            WHERE field_key = ? AND value = ? AND source = 'user_submission'
            """,
            (flag, row["field_key"], row["proposed_value"]),
        )
    return {
        "submission_id": submission_id,
        "field_key": row["field_key"],
        "proposed_value": row["proposed_value"],
        "is_approved": is_approved,
    }


def get_style_tags_payload(style_id: str) -> dict[str, Any] | None:
    with connect_db() as conn:
        _ensure_tables(conn)
        row = conn.execute(
            "SELECT tags_json FROM styles WHERE style_id = ?",
            (style_id,),
        ).fetchone()
        if not row:
            return None
        tags_json = json.loads(row["tags_json"] or "{}")
        tag_rows = conn.execute(
            "SELECT tag_type, tag_value FROM style_tags WHERE style_id = ?",
            (style_id,),
        ).fetchall()
    merged = _merge_v2_tags(tags_json, tag_rows)
    return validate_style_tags(merged)


def _merge_v2_tags(tags_json: dict[str, Any], tag_rows: list[sqlite3.Row]) -> dict[str, Any]:
    merged: dict[str, list[str]] = {}
    for key, values in tags_json.items():
        if isinstance(values, list):
            merged[key] = list(values)
        elif isinstance(values, str) and values:
            merged[key] = [values]
    for row in tag_rows:
        merged.setdefault(row["tag_type"], [])
        if row["tag_value"] not in merged[row["tag_type"]]:
            merged[row["tag_type"]].append(row["tag_value"])
    flat: dict[str, Any] = storage_dict_to_style_tags(merged)
    if "candidate_tags" in tags_json:
        flat["candidate_tags"] = tags_json.get("candidate_tags", [])
    return flat


def _ensure_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS taxonomy_fields (
            field_key TEXT PRIMARY KEY,
            label_cn TEXT NOT NULL,
            value_type TEXT NOT NULL,
            dimension TEXT NOT NULL,
            sort_order INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS taxonomy_options (
            option_id TEXT PRIMARY KEY,
            field_key TEXT NOT NULL,
            value TEXT NOT NULL,
            is_approved INTEGER NOT NULL DEFAULT 1,
            source TEXT NOT NULL DEFAULT 'seed_v2',
            created_at TEXT NOT NULL,
            UNIQUE(field_key, value),
            FOREIGN KEY(field_key) REFERENCES taxonomy_fields(field_key)
        );

        CREATE TABLE IF NOT EXISTS taxonomy_submissions (
            submission_id TEXT PRIMARY KEY,
            field_key TEXT NOT NULL,
            proposed_value TEXT NOT NULL,
            submitted_by TEXT,
            is_approved INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY(field_key) REFERENCES taxonomy_fields(field_key)
        );
        """
    )
