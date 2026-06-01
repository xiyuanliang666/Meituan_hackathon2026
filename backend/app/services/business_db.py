import json
import sqlite3
from uuid import uuid4
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from app.config import get_settings
from app.data.nail_taxonomy_v2_seed import STYLE_TAG_FIELD_KEYS
from app.services.dataset_loader import load_evaluation_dataset


@contextmanager
def connect_db() -> Iterator[sqlite3.Connection]:
    path = _database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db(seed: bool = True) -> dict[str, int]:
    with connect_db() as conn:
        _create_tables(conn)
        from app.services.taxonomy_store import ensure_taxonomy_seeded

        ensure_taxonomy_seeded(conn)
        if seed:
            _seed_from_xlsx(conn)
        return get_db_summary(conn)


def get_db_summary(conn: sqlite3.Connection | None = None) -> dict[str, int]:
    if conn is None:
        with connect_db() as owned_conn:
            return get_db_summary(owned_conn)

    tables = [
        "hand_templates",
        "styles",
        "evaluation_pairs",
        "style_composites",
        "style_tags",
        "style_signals",
        "ugc_keywords",
        "user_events",
        "push_audits",
        "report_snapshots",
        "user_tryon_history",
        "taxonomy_fields",
        "taxonomy_options",
        "taxonomy_submissions",
    ]
    return {table: _count_rows(conn, table) for table in tables}


def list_styles(limit: int = 50, status: str | None = None, q: str | None = None) -> list[dict[str, Any]]:
    with connect_db() as conn:
        _create_tables(conn)
        clauses = ["COALESCE(status, 'active') != 'deleted'"]
        params: list[Any] = []
        if status:
            clauses.append("COALESCE(status, 'active') = ?")
            params.append(status)
        if q:
            clauses.append("(style_name LIKE ? OR tags_json LIKE ?)")
            params.extend([f"%{q}%", f"%{q}%"])
        params.append(limit)
        rows = conn.execute(
            f"""
            SELECT style_id, original_style_image_url, enhanced_style_image_url,
                   style_name, tags_json, hot_score, life_cycle, tryon_enabled,
                   status, review_status, source, created_at
            FROM styles
            WHERE {' AND '.join(clauses)}
            ORDER BY style_id
            LIMIT ?
            """,
            params,
        ).fetchall()

    styles = []
    for row in rows:
        item = dict(row)
        raw_tags = json.loads(item.pop("tags_json") or "{}")
        # 确保所有 tag 值都是 list（enum 单选字段存为 string，需转 list）
        # 并按业务优先级排序：颜色体系 > 风格标签 > 场景标签 > 季节标签 > ...
        normalized_tags = {}
        for k, v in raw_tags.items():
            if isinstance(v, list):
                normalized_tags[k] = v
            elif isinstance(v, str) and v:
                normalized_tags[k] = [v]
            else:
                normalized_tags[k] = []
        sorted_tags = {}
        for key in STYLE_TAG_FIELD_KEYS:
            if key in normalized_tags:
                sorted_tags[key] = normalized_tags[key]
        for key in normalized_tags:
            if key not in sorted_tags:
                sorted_tags[key] = normalized_tags[key]
        item["tags"] = sorted_tags
        styles.append(item)
    return styles


def list_recommendation_candidates(limit: int = 200) -> list[dict[str, Any]]:
    init_db(seed=True)
    with connect_db() as conn:
        rows = conn.execute(
            """
            SELECT style_id, style_name, enhanced_style_image_url,
                   tags_json, hot_score, life_cycle
            FROM styles
            WHERE COALESCE(status, 'active') != 'deleted'
            ORDER BY hot_score DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        candidates: list[dict[str, Any]] = []
        for row in rows:
            style = dict(row)
            tags = json.loads(style.pop("tags_json") or "{}")
            tag_rows = conn.execute(
                """
                SELECT tag_type, tag_value
                FROM style_tags
                WHERE style_id = ?
                """,
                (style["style_id"],),
            ).fetchall()
            signal_rows = conn.execute(
                """
                SELECT signal, value, delta, weight
                FROM style_signals
                WHERE style_id = ?
                """,
                (style["style_id"],),
            ).fetchall()
            candidates.append(
                {
                    **style,
                    "tags": _merge_tags(tags, tag_rows),
                    "signals": [dict(signal_row) for signal_row in signal_rows],
                }
            )
    return candidates


def list_events(limit: int = 50) -> list[dict[str, Any]]:
    with connect_db() as conn:
        _create_tables(conn)
        rows = conn.execute(
            """
            SELECT event_id, user_id, style_id, hand_template_id,
                   event_type, source, created_at
            FROM user_events
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def create_event(
    event_type: str,
    user_id: str | None = None,
    style_id: str | None = None,
    hand_template_id: str | None = None,
    source: str = "demo",
) -> dict[str, Any]:
    init_db(seed=True)
    event_id = "evt-" + uuid4().hex[:12]
    created_at = _now()
    with connect_db() as conn:
        conn.execute(
            """
            INSERT INTO user_events
            (event_id, user_id, style_id, hand_template_id, event_type, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (event_id, user_id, style_id, hand_template_id, event_type, source, created_at),
        )
    return {
        "event_id": event_id,
        "user_id": user_id,
        "style_id": style_id,
        "hand_template_id": hand_template_id,
        "event_type": event_type,
        "source": source,
        "created_at": created_at,
    }


def list_event_stats(limit: int = 50) -> list[dict[str, Any]]:
    init_db(seed=True)
    with connect_db() as conn:
        rows = conn.execute(
            """
            SELECT
                s.style_id,
                s.style_name,
                SUM(CASE WHEN e.event_type = 'exposure' THEN 1 ELSE 0 END) AS exposure_count,
                SUM(CASE WHEN e.event_type = 'try_on' THEN 1 ELSE 0 END) AS try_on_count,
                SUM(CASE WHEN e.event_type = 'favorite' THEN 1 ELSE 0 END) AS favorite_count,
                SUM(CASE WHEN e.event_type = 'like' THEN 1 ELSE 0 END) AS like_count,
                SUM(CASE WHEN e.event_type = 'dislike' THEN 1 ELSE 0 END) AS dislike_count,
                SUM(CASE WHEN e.event_type = 'order' THEN 1 ELSE 0 END) AS order_count
            FROM styles s
            LEFT JOIN user_events e ON e.style_id = s.style_id
            WHERE COALESCE(s.status, 'active') != 'deleted'
            GROUP BY s.style_id, s.style_name
            HAVING exposure_count + try_on_count + favorite_count + like_count + dislike_count + order_count > 0
            ORDER BY try_on_count DESC, favorite_count DESC, order_count DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    stats = []
    for row in rows:
        item = dict(row)
        exposure_count = int(item["exposure_count"] or 0)
        try_on_count = int(item["try_on_count"] or 0)
        favorite_count = int(item["favorite_count"] or 0)
        order_count = int(item["order_count"] or 0)
        item["try_rate"] = _safe_rate(try_on_count, exposure_count)
        item["favorite_rate"] = _safe_rate(favorite_count, try_on_count)
        item["order_rate"] = _safe_rate(order_count, try_on_count)
        stats.append(item)
    return stats


def list_hot_push_candidates(limit: int = 10) -> list[dict[str, Any]]:
    init_db(seed=True)
    with connect_db() as conn:
        rows = conn.execute(
            """
            SELECT style_id, style_name, enhanced_style_image_url,
                   tags_json, hot_score, life_cycle
            FROM styles
            WHERE COALESCE(status, 'active') != 'deleted'
            ORDER BY hot_score DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        candidates: list[dict[str, Any]] = []
        for row in rows:
            style = dict(row)
            tags = json.loads(style.pop("tags_json") or "{}")
            tag_rows = conn.execute(
                "SELECT tag_type, tag_value FROM style_tags WHERE style_id = ?",
                (style["style_id"],),
            ).fetchall()
            signal_rows = conn.execute(
                "SELECT signal, value, delta, weight FROM style_signals WHERE style_id = ?",
                (style["style_id"],),
            ).fetchall()
            event_stats = _event_stats_for_style(conn, style["style_id"])
            audit_row = conn.execute(
                """
                SELECT status, selected_image_url, selected_coupon_url, final_tagline,
                       final_price, updated_at
                FROM push_audits
                WHERE push_id = ?
                """,
                (_push_id_for_style(style["style_id"]),),
            ).fetchone()
            candidates.append(
                {
                    **style,
                    "push_id": _push_id_for_style(style["style_id"]),
                    "tags": _merge_tags(tags, tag_rows),
                    "signals": [dict(signal_row) for signal_row in signal_rows],
                    "event_stats": event_stats,
                    "status": audit_row["status"] if audit_row else "pending",
                    "audit_details": dict(audit_row) if audit_row else {},
                }
            )
    return candidates


def upsert_push_audit(
    push_id: str,
    style_id: str,
    merchant_id: str,
    status: str,
    selected_image_url: str | None = None,
    selected_coupon_url: str | None = None,
    final_tagline: str | None = None,
    final_price: float | None = None,
) -> dict[str, Any]:
    init_db(seed=True)
    now = _now()
    with connect_db() as conn:
        conn.execute(
            """
            INSERT INTO push_audits
            (push_id, style_id, merchant_id, status, selected_image_url, selected_coupon_url,
             final_tagline, final_price, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(push_id) DO UPDATE SET
                merchant_id = excluded.merchant_id,
                status = excluded.status,
                selected_image_url = excluded.selected_image_url,
                selected_coupon_url = excluded.selected_coupon_url,
                final_tagline = excluded.final_tagline,
                final_price = excluded.final_price,
                updated_at = excluded.updated_at
            """,
            (
                push_id,
                style_id,
                merchant_id,
                status,
                selected_image_url,
                selected_coupon_url,
                final_tagline,
                final_price,
                now,
            ),
        )
        if status == "published":
            conn.execute("UPDATE styles SET tryon_enabled = 1 WHERE style_id = ?", (style_id,))
        row = conn.execute(
            """
            SELECT push_id, style_id, merchant_id, status, selected_image_url, selected_coupon_url,
                   final_tagline, final_price, updated_at
            FROM push_audits
            WHERE push_id = ?
            """,
            (push_id,),
        ).fetchone()
    return dict(row) if row else {}


def upsert_style_tags(
    style_id: str,
    tags: dict[str, list[str]],
    analysis_mode: str,
    style_name: str | None = None,
    tags_json_full: dict[str, Any] | None = None,
) -> None:
    init_db(seed=True)
    now = _now()
    with connect_db() as conn:
        if style_name:
            conn.execute("UPDATE styles SET style_name = ? WHERE style_id = ?", (style_name, style_id))
        payload = tags_json_full if tags_json_full is not None else tags
        conn.execute(
            """
            UPDATE styles
            SET tags_json = ?
            WHERE style_id = ?
            """,
            (json.dumps(payload, ensure_ascii=False), style_id),
        )
        conn.execute("DELETE FROM style_tags WHERE style_id = ?", (style_id,))
        for tag_type, values in tags.items():
            if tag_type == "candidate_tags":
                continue
            for value in values:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO style_tags
                    (style_id, tag_type, tag_value, source, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (style_id, tag_type, value, analysis_mode, now),
                )


def get_style(style_id: str) -> dict[str, Any] | None:
    init_db(seed=True)
    with connect_db() as conn:
        row = conn.execute(
            """
            SELECT style_id, original_style_image_url, enhanced_style_image_url,
                   style_name, tags_json, hot_score, life_cycle, tryon_enabled,
                   status, review_status, source, created_at
            FROM styles
            WHERE style_id = ? AND COALESCE(status, 'active') != 'deleted'
            """,
            (style_id,),
        ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["tags"] = json.loads(item.pop("tags_json") or "{}")
        return item


# ===== 款式 CRUD (B1/B2/B3) =====

def create_style(
    style_name: str,
    image_url: str,
    tags: dict[str, Any] | None = None,
    status: str = "active",
    review_status: str = "merchant_confirmed",
) -> dict[str, Any]:
    """创建新款式并入库"""
    from app.services.taxonomy_store import style_tags_to_storage_dict, validate_style_tags

    style_id = f"style-{uuid4().hex[:10]}"
    now = _now()
    normalized_tags = validate_style_tags(tags or {})
    tags_json = json.dumps(normalized_tags, ensure_ascii=False)
    with connect_db() as conn:
        _create_tables(conn)
        conn.execute(
            """
            INSERT INTO styles
            (style_id, enhanced_style_image_url, style_name, tags_json, source, status, review_status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (style_id, image_url, style_name, tags_json, "merchant_upload", status, review_status, now),
        )
        for tag_type, values in style_tags_to_storage_dict(normalized_tags).items():
            for value in values:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO style_tags
                    (style_id, tag_type, tag_value, source, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (style_id, tag_type, value, "merchant_upload", now),
                )
    return {
        "style_id": style_id,
        "style_name": style_name,
        "image_url": image_url,
        "tags": normalized_tags,
        "tryon_enabled": True,
        "status": status,
        "review_status": review_status,
        "created_at": now,
    }


def delete_style(style_id: str) -> bool:
    """软删除款式，列表默认不再返回。"""
    with connect_db() as conn:
        _create_tables(conn)
        existing = conn.execute(
            "SELECT 1 FROM styles WHERE style_id = ? AND COALESCE(status, 'active') != 'deleted'",
            (style_id,),
        ).fetchone()
        if not existing:
            return False
        conn.execute("UPDATE styles SET status = 'deleted', deleted_at = ? WHERE style_id = ?", (_now(), style_id))
    return True


def batch_delete_styles(style_ids: list[str]) -> dict[str, Any]:
    deleted = 0
    for style_id in style_ids:
        if delete_style(style_id):
            deleted += 1
    return {"requested": len(style_ids), "deleted": deleted}


def update_style(style_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    """更新款式信息（名称、图片、标签、tryon_enabled等）"""
    from app.services.taxonomy_store import style_tags_to_storage_dict, validate_style_tags

    found = False
    with connect_db() as conn:
        _create_tables(conn)
        row = conn.execute("SELECT * FROM styles WHERE style_id = ?", (style_id,)).fetchone()
        if not row:
            return None
        found = True
        sets = []
        params: list[Any] = []
        normalized_tags: dict[str, Any] | None = None
        if "style_name" in updates:
            sets.append("style_name = ?")
            params.append(updates["style_name"])
        if "image_url" in updates:
            sets.append("enhanced_style_image_url = ?")
            params.append(updates["image_url"])
        if "tags" in updates:
            normalized_tags = validate_style_tags(updates["tags"] or {})
            sets.append("tags_json = ?")
            params.append(json.dumps(normalized_tags, ensure_ascii=False))
        if "life_cycle" in updates:
            sets.append("life_cycle = ?")
            params.append(updates["life_cycle"])
        if "tryon_enabled" in updates:
            sets.append("tryon_enabled = ?")
            params.append(1 if updates["tryon_enabled"] else 0)
        if "status" in updates:
            sets.append("status = ?")
            params.append(updates["status"])
        if "review_status" in updates:
            sets.append("review_status = ?")
            params.append(updates["review_status"])
        if sets:
            params.append(style_id)
            conn.execute(f"UPDATE styles SET {', '.join(sets)} WHERE style_id = ?", params)
        if normalized_tags is not None:
            conn.execute("DELETE FROM style_tags WHERE style_id = ?", (style_id,))
            for tag_type, values in style_tags_to_storage_dict(normalized_tags).items():
                for value in values:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO style_tags
                        (style_id, tag_type, tag_value, source, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (style_id, tag_type, value, "style_update", _now()),
                    )
    return get_style(style_id) if found else None


# ===== 模板 CRUD (B5/B6/B7/B8) =====

def list_templates(source: str | None = None) -> list[dict[str, Any]]:
    """获取裸手模板列表"""
    with connect_db() as conn:
        _create_tables(conn)
        if source:
            rows = conn.execute(
                """
                SELECT hand_template_id, hand_image_url, label, skin_tone, hand_shape,
                       recommended_colors_json, recommended_styles_json,
                       recommended_nail_shapes_json, analysis_reason, analysis_mode,
                       source, created_at
                FROM hand_templates
                WHERE source = ? AND source != 'deleted'
                ORDER BY created_at DESC
                """,
                (source,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT hand_template_id, hand_image_url, label, skin_tone, hand_shape,
                       recommended_colors_json, recommended_styles_json,
                       recommended_nail_shapes_json, analysis_reason, analysis_mode,
                       source, created_at
                FROM hand_templates
                WHERE source NOT IN ('public', 'deleted')
                ORDER BY created_at DESC
                """
            ).fetchall()
    return [_template_payload(dict(r)) for r in rows]


def list_seed_hand_templates(limit: int | None = None) -> list[dict[str, Any]]:
    with connect_db() as conn:
        _create_tables(conn)
        rows = conn.execute(
            """
            SELECT hand_template_id, hand_image_url, label, skin_tone, hand_shape,
                   recommended_colors_json, recommended_styles_json,
                   recommended_nail_shapes_json, analysis_reason, analysis_mode,
                   source, created_at
            FROM hand_templates
            WHERE source = 'seed_xlsx'
            ORDER BY hand_template_id
            """
        ).fetchall()
    items = [dict(row) for row in rows]
    if limit:
        return items[:limit]
    return items


def update_hand_template_analysis(
    template_id: str,
    skin_tone: str,
    hand_shape: str,
    recommended_colors: list[str],
    recommended_styles: list[str],
    recommended_nail_shapes: list[str],
    analysis_reason: str,
    analysis_mode: str,
) -> None:
    with connect_db() as conn:
        _create_tables(conn)
        conn.execute(
            """
            UPDATE hand_templates
            SET skin_tone = ?,
                hand_shape = ?,
                recommended_colors_json = ?,
                recommended_styles_json = ?,
                recommended_nail_shapes_json = ?,
                analysis_reason = ?,
                analysis_mode = ?
            WHERE hand_template_id = ?
            """,
            (
                skin_tone,
                hand_shape,
                json.dumps(recommended_colors, ensure_ascii=False),
                json.dumps(recommended_styles, ensure_ascii=False),
                json.dumps(recommended_nail_shapes, ensure_ascii=False),
                analysis_reason,
                analysis_mode,
                template_id,
            ),
        )


def create_template(
    image_url: str,
    label: str = "",
    source: str = "merchant",
    skin_tone: str = "",
    hand_shape: str = "",
) -> dict[str, Any]:
    """创建裸手模板"""
    now = _now()
    with connect_db() as conn:
        _create_tables(conn)
        existing = conn.execute(
            """
            SELECT hand_template_id, hand_image_url, label, skin_tone, hand_shape, source, created_at
            FROM hand_templates
            WHERE hand_image_url = ?
            """,
            (image_url,),
        ).fetchone()
        if existing:
            if label and label != existing["label"]:
                conn.execute(
                    "UPDATE hand_templates SET label = ? WHERE hand_template_id = ?",
                    (label, existing["hand_template_id"]),
                )
                existing = conn.execute(
                    """
                    SELECT hand_template_id, hand_image_url, label, skin_tone, hand_shape, source, created_at
                    FROM hand_templates
                    WHERE hand_template_id = ?
                    """,
                    (existing["hand_template_id"],),
                ).fetchone()
            return dict(existing)
        template_id = f"tpl-{uuid4().hex[:10]}"
        conn.execute(
            """
            INSERT INTO hand_templates
            (hand_template_id, hand_image_url, label, skin_tone, hand_shape, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (template_id, image_url, label, skin_tone, hand_shape, source, now),
        )
    return {
        "hand_template_id": template_id,
        "hand_image_url": image_url,
        "label": label,
        "skin_tone": skin_tone,
        "hand_shape": hand_shape,
        "source": source,
        "created_at": now,
    }


def delete_template(template_id: str) -> bool:
    """删除裸手模板"""
    with connect_db() as conn:
        _create_tables(conn)
        existing = conn.execute(
            """
            SELECT source FROM hand_templates
            WHERE hand_template_id = ?
            """,
            (template_id,),
        ).fetchone()
        if not existing:
            return False
        if existing["source"] not in {"merchant", "merchant_upload"}:
            raise PermissionError("public template is read-only")
        conn.execute("UPDATE hand_templates SET source = 'deleted' WHERE hand_template_id = ?", (template_id,))
    return True


def update_template(template_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    allowed = {"label", "skin_tone", "hand_shape", "analysis_reason"}
    with connect_db() as conn:
        _create_tables(conn)
        row = conn.execute(
            """
            SELECT hand_template_id, source
            FROM hand_templates
            WHERE hand_template_id = ?
            """,
            (template_id,),
        ).fetchone()
        if not row:
            return None
        if row["source"] not in {"merchant", "merchant_upload"}:
            raise PermissionError("public template is read-only")
        sets = []
        params: list[Any] = []
        for key, value in updates.items():
            if key in allowed:
                sets.append(f"{key} = ?")
                params.append(str(value or "").strip())
        if sets:
            params.append(template_id)
            conn.execute(f"UPDATE hand_templates SET {', '.join(sets)} WHERE hand_template_id = ?", params)
    return get_template_by_id(template_id)


# 公共模板库（硬编码）
PUBLIC_TEMPLATES = [
    {"hand_template_id": "pub-01", "hand_image_url": "http://p0.meituan.net/pilotimages/b9632e3a699fdb63a1a6139bbfd6bf0d2159483.png", "label": "自然肤色A", "skin_tone": "自然肤色", "hand_shape": "标准", "source": "public", "created_at": ""},
    {"hand_template_id": "pub-02", "hand_image_url": "http://p1.meituan.net/pilotimages/704b1c4bdf589b5d5367f2748f6868f42205269.png", "label": "自然肤色B", "skin_tone": "自然肤色", "hand_shape": "修长", "source": "public", "created_at": ""},
    {"hand_template_id": "pub-03", "hand_image_url": "http://p0.meituan.net/pilotimages/3cd4bc446f321574df68ce0a749b16b62603765.png", "label": "白皙肤色A", "skin_tone": "白皙肤色", "hand_shape": "标准", "source": "public", "created_at": ""},
    {"hand_template_id": "pub-04", "hand_image_url": "http://p0.meituan.net/pilotimages/7c791f4b4b13659d62d991f172f5ffd02674881.png", "label": "白皙肤色B", "skin_tone": "白皙肤色", "hand_shape": "修长", "source": "public", "created_at": ""},
    {"hand_template_id": "pub-05", "hand_image_url": "http://p1.meituan.net/pilotimages/5a7efacd78020469ab44e4caca1afe972676586.png", "label": "暖肤色A", "skin_tone": "暖肤色", "hand_shape": "标准", "source": "public", "created_at": ""},
    {"hand_template_id": "pub-06", "hand_image_url": "http://p1.meituan.net/pilotimages/6a3d032df4a143c79c3e2ec3cd4c53522723999.png", "label": "暖肤色B", "skin_tone": "暖肤色", "hand_shape": "修长", "source": "public", "created_at": ""},
    {"hand_template_id": "pub-07", "hand_image_url": "http://p0.meituan.net/pilotimages/ed9a1cd3cca3997ede3779771dda6a772149757.png", "label": "冷白肤色", "skin_tone": "冷白肤色", "hand_shape": "标准", "source": "public", "created_at": ""},
    {"hand_template_id": "pub-08", "hand_image_url": "http://p1.meituan.net/pilotimages/a52c995f1f9e2e668c6093099cfd24032514125.png", "label": "深肤色", "skin_tone": "深肤色", "hand_shape": "标准", "source": "public", "created_at": ""},
]


def list_public_templates() -> list[dict[str, Any]]:
    init_db(seed=True)
    templates = list_seed_hand_templates()
    return [_template_payload(item) for item in templates]


def _template_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "hand_template_id": item["hand_template_id"],
        "hand_image_url": item["hand_image_url"],
        "label": item.get("label", "") or item["hand_template_id"],
        "skin_tone": item.get("skin_tone", "") or "未分析",
        "hand_shape": item.get("hand_shape", ""),
        "source": item.get("source", ""),
        "created_at": item.get("created_at", ""),
        "recommended_colors": _json_list(item.get("recommended_colors_json")),
        "recommended_styles": _json_list(item.get("recommended_styles_json")),
        "recommended_nail_shapes": _json_list(item.get("recommended_nail_shapes_json")),
        "analysis_reason": item.get("analysis_reason", ""),
        "analysis_mode": item.get("analysis_mode", ""),
    }


def _json_list(value: Any) -> list[str]:
    if not value:
        return []
    try:
        data = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return [str(item) for item in data] if isinstance(data, list) else []


def get_template_by_id(template_id: str) -> dict[str, Any] | None:
    with connect_db() as conn:
        _create_tables(conn)
        row = conn.execute(
            """
            SELECT hand_template_id, hand_image_url, label, skin_tone, hand_shape,
                   recommended_colors_json, recommended_styles_json,
                   recommended_nail_shapes_json, analysis_reason, analysis_mode,
                   source, created_at
            FROM hand_templates
            WHERE hand_template_id = ?
            """,
            (template_id,),
        ).fetchone()
    if row:
        return _template_payload(dict(row))
    for template in PUBLIC_TEMPLATES:
        if template["hand_template_id"] == template_id:
            return template
    return None


def save_style_composite(
    style_id: str,
    template_id: str,
    template_image_url: str,
    result_image_url: str,
    generation_mode: str,
    status: str = "generated",
) -> dict[str, Any]:
    composite_id = f"cmp-{uuid4().hex[:12]}"
    now = _now()
    with connect_db() as conn:
        _create_tables(conn)
        conn.execute(
            """
            INSERT INTO style_composites
            (composite_id, style_id, template_id, template_image_url, result_image_url,
             generation_mode, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (composite_id, style_id, template_id, template_image_url, result_image_url, generation_mode, status, now),
        )
    return {
        "composite_id": composite_id,
        "style_id": style_id,
        "template_id": template_id,
        "template_image_url": template_image_url,
        "result_image_url": result_image_url,
        "generation_mode": generation_mode,
        "status": status,
        "created_at": now,
    }


def list_style_composites(style_id: str, status: str | None = None) -> list[dict[str, Any]]:
    with connect_db() as conn:
        _create_tables(conn)
        if status:
            rows = conn.execute(
                """
                SELECT composite_id, style_id, template_id, template_image_url, result_image_url,
                       generation_mode, status, created_at
                FROM style_composites
                WHERE style_id = ? AND status = ?
                ORDER BY created_at DESC
                """,
                (style_id, status),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT composite_id, style_id, template_id, template_image_url, result_image_url,
                       generation_mode, status, created_at
                FROM style_composites
                WHERE style_id = ?
                ORDER BY created_at DESC
                """,
                (style_id,),
            ).fetchall()
    return [dict(row) for row in rows]


def update_style_composite_selection(style_id: str, selected_ids: list[str]) -> dict[str, Any]:
    with connect_db() as conn:
        _create_tables(conn)
        conn.execute(
            "UPDATE style_composites SET status = 'rejected' WHERE style_id = ?",
            (style_id,),
        )
        for composite_id in selected_ids:
            conn.execute(
                "UPDATE style_composites SET status = 'selected' WHERE style_id = ? AND composite_id = ?",
                (style_id, composite_id),
            )
    return {"style_id": style_id, "selected_count": len(selected_ids)}


def create_report_snapshot(
    merchant_id: str | None,
    period: str,
    merchant_prefs: dict[str, Any],
    current_period: dict[str, Any],
    last_period: dict[str, Any],
    metrics: list[dict[str, Any]],
    hot_styles: list[dict[str, Any]],
    suggestions: list[dict[str, Any]],
    report_summary: str,
    generation_mode: str,
) -> dict[str, Any]:
    init_db(seed=True)
    snapshot_id = f"report-{uuid4().hex[:12]}"
    now = _now()
    with connect_db() as conn:
        conn.execute(
            """
            INSERT INTO report_snapshots
            (snapshot_id, merchant_id, period, merchant_prefs_json, current_period_json,
             last_period_json, metrics_json, hot_styles_json, suggestions_json,
             report_summary, generation_mode, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                merchant_id or "",
                period,
                json.dumps(merchant_prefs, ensure_ascii=False),
                json.dumps(current_period, ensure_ascii=False),
                json.dumps(last_period, ensure_ascii=False),
                json.dumps(metrics, ensure_ascii=False),
                json.dumps(hot_styles, ensure_ascii=False),
                json.dumps(suggestions, ensure_ascii=False),
                report_summary,
                generation_mode,
                now,
                now,
            ),
    )
    return {"snapshot_id": snapshot_id, "created_at": now}


def list_report_snapshots(limit: int = 20) -> list[dict[str, Any]]:
    with connect_db() as conn:
        _create_tables(conn)
        rows = conn.execute(
            """
            SELECT snapshot_id, merchant_id, period, report_summary, generation_mode, created_at
            FROM report_snapshots
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


# ===== Taxonomy 模糊搜索 (B9) =====

def search_taxonomy_options(field_key: str, query: str, limit: int = 20) -> list[dict[str, Any]]:
    """按字段+关键词模糊搜索已审批标签值"""
    with connect_db() as conn:
        _create_tables(conn)
        rows = conn.execute(
            """
            SELECT option_id, field_key, value, is_approved, source
            FROM taxonomy_options
            WHERE field_key = ? AND value LIKE ? AND is_approved = 1
            LIMIT ?
            """,
            (field_key, f"%{query}%", limit),
        ).fetchall()
    return [dict(r) for r in rows]


def _create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS hand_templates (
            hand_template_id TEXT PRIMARY KEY,
            hand_image_url TEXT NOT NULL UNIQUE,
            label TEXT NOT NULL DEFAULT '',
            skin_tone TEXT NOT NULL DEFAULT '',
            hand_shape TEXT NOT NULL DEFAULT '',
            recommended_colors_json TEXT NOT NULL DEFAULT '[]',
            recommended_styles_json TEXT NOT NULL DEFAULT '[]',
            recommended_nail_shapes_json TEXT NOT NULL DEFAULT '[]',
            analysis_reason TEXT NOT NULL DEFAULT '',
            analysis_mode TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT 'seed_xlsx',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS styles (
            style_id TEXT PRIMARY KEY,
            original_style_image_url TEXT,
            enhanced_style_image_url TEXT NOT NULL UNIQUE,
            style_name TEXT,
            tags_json TEXT NOT NULL DEFAULT '{}',
            hot_score REAL NOT NULL DEFAULT 0,
            life_cycle TEXT NOT NULL DEFAULT '观察期',
            tryon_enabled INTEGER NOT NULL DEFAULT 1,
            source TEXT NOT NULL DEFAULT 'seed_xlsx',
            status TEXT NOT NULL DEFAULT 'active',
            review_status TEXT NOT NULL DEFAULT 'merchant_confirmed',
            deleted_at TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS style_composites (
            composite_id TEXT PRIMARY KEY,
            style_id TEXT NOT NULL,
            template_id TEXT NOT NULL,
            template_image_url TEXT NOT NULL,
            result_image_url TEXT NOT NULL,
            generation_mode TEXT NOT NULL DEFAULT 'mock',
            status TEXT NOT NULL DEFAULT 'generated',
            created_at TEXT NOT NULL,
            FOREIGN KEY(style_id) REFERENCES styles(style_id)
        );

        CREATE TABLE IF NOT EXISTS evaluation_pairs (
            pair_id TEXT PRIMARY KEY,
            hand_template_id TEXT NOT NULL,
            style_id TEXT NOT NULL,
            hand_image_url TEXT NOT NULL,
            style_image_url TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'seed_xlsx',
            created_at TEXT NOT NULL,
            FOREIGN KEY(hand_template_id) REFERENCES hand_templates(hand_template_id),
            FOREIGN KEY(style_id) REFERENCES styles(style_id)
        );

        CREATE TABLE IF NOT EXISTS style_tags (
            style_id TEXT NOT NULL,
            tag_type TEXT NOT NULL,
            tag_value TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'seed_or_mock',
            created_at TEXT NOT NULL,
            PRIMARY KEY(style_id, tag_type, tag_value),
            FOREIGN KEY(style_id) REFERENCES styles(style_id)
        );

        CREATE TABLE IF NOT EXISTS style_signals (
            style_id TEXT NOT NULL,
            signal TEXT NOT NULL,
            value REAL NOT NULL,
            delta REAL NOT NULL DEFAULT 0,
            weight REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            PRIMARY KEY(style_id, signal),
            FOREIGN KEY(style_id) REFERENCES styles(style_id)
        );

        CREATE TABLE IF NOT EXISTS ugc_keywords (
            keyword TEXT PRIMARY KEY,
            heat_score REAL NOT NULL,
            delta REAL NOT NULL DEFAULT 0,
            related_tags_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS user_events (
            event_id TEXT PRIMARY KEY,
            user_id TEXT,
            style_id TEXT,
            hand_template_id TEXT,
            event_type TEXT NOT NULL,
            source TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS push_audits (
            push_id TEXT PRIMARY KEY,
            style_id TEXT NOT NULL,
            merchant_id TEXT NOT NULL,
            status TEXT NOT NULL,
            selected_image_url TEXT,
            selected_coupon_url TEXT,
            final_tagline TEXT,
            final_price REAL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(style_id) REFERENCES styles(style_id)
        );

        CREATE TABLE IF NOT EXISTS report_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            merchant_id TEXT NOT NULL DEFAULT '',
            period TEXT NOT NULL,
            merchant_prefs_json TEXT NOT NULL DEFAULT '{}',
            current_period_json TEXT NOT NULL DEFAULT '{}',
            last_period_json TEXT NOT NULL DEFAULT '{}',
            metrics_json TEXT NOT NULL DEFAULT '[]',
            hot_styles_json TEXT NOT NULL DEFAULT '[]',
            suggestions_json TEXT NOT NULL DEFAULT '[]',
            report_summary TEXT NOT NULL DEFAULT '',
            generation_mode TEXT NOT NULL DEFAULT 'mock',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS user_tryon_history (
            record_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            hand_id TEXT,
            style_id TEXT,
            hand_image_url TEXT NOT NULL,
            style_image_url TEXT NOT NULL,
            result_image_url TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    _ensure_schema_upgrades(conn)


def _ensure_schema_upgrades(conn: sqlite3.Connection) -> None:
    _ensure_column(conn, "hand_templates", "label", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "hand_templates", "skin_tone", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "hand_templates", "hand_shape", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "hand_templates", "recommended_colors_json", "TEXT NOT NULL DEFAULT '[]'")
    _ensure_column(conn, "hand_templates", "recommended_styles_json", "TEXT NOT NULL DEFAULT '[]'")
    _ensure_column(conn, "hand_templates", "recommended_nail_shapes_json", "TEXT NOT NULL DEFAULT '[]'")
    _ensure_column(conn, "hand_templates", "analysis_reason", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "hand_templates", "analysis_mode", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "styles", "tryon_enabled", "INTEGER NOT NULL DEFAULT 1")
    _ensure_column(conn, "styles", "status", "TEXT NOT NULL DEFAULT 'active'")
    _ensure_column(conn, "styles", "review_status", "TEXT NOT NULL DEFAULT 'merchant_confirmed'")
    _ensure_column(conn, "styles", "deleted_at", "TEXT")
    _ensure_column(conn, "push_audits", "selected_image_url", "TEXT")
    _ensure_column(conn, "push_audits", "selected_coupon_url", "TEXT")
    _ensure_column(conn, "push_audits", "final_tagline", "TEXT")
    _ensure_column(conn, "push_audits", "final_price", "REAL")


def _ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, definition: str) -> None:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    if any(row["name"] == column_name for row in rows):
        return
    conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def _seed_from_xlsx(conn: sqlite3.Connection) -> None:
    dataset = load_evaluation_dataset()
    now = _now()

    for index, hand_url in enumerate(dataset.hand_templates, start=1):
        conn.execute(
            """
            INSERT OR IGNORE INTO hand_templates
            (hand_template_id, hand_image_url, label, source, created_at)
            VALUES (?, ?, ?, 'merchant', ?)
            """,
            (f"hand-seed-{index:03d}", hand_url, f"种子模板 {index:03d}", now),
        )

    for style in dataset.styles:
        conn.execute(
            """
            INSERT OR IGNORE INTO styles
            (style_id, original_style_image_url, enhanced_style_image_url,
             style_name, tags_json, hot_score, life_cycle, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'seed_xlsx', ?)
            """,
            (
                style.style_id,
                style.original_style_image_url,
                style.enhanced_style_image_url,
                f"种子款式 {style.style_id[-3:]}",
                json.dumps(_seed_tags_for_style(style.style_id), ensure_ascii=False),
                _seed_hot_score(style.style_id),
                _seed_life_cycle(style.style_id),
                now,
            ),
        )
        _seed_style_tags(conn, style.style_id, now)
        _seed_style_signals(conn, style.style_id, now)

    style_by_url = {style.enhanced_style_image_url: style.style_id for style in dataset.styles}
    hand_by_url = {
        hand_url: f"hand-seed-{index:03d}"
        for index, hand_url in enumerate(dataset.hand_templates, start=1)
    }
    for pair in dataset.pairs:
        conn.execute(
            """
            INSERT OR IGNORE INTO evaluation_pairs
            (pair_id, hand_template_id, style_id, hand_image_url,
             style_image_url, source, created_at)
            VALUES (?, ?, ?, ?, ?, 'seed_xlsx', ?)
            """,
            (
                pair.pair_id,
                hand_by_url[pair.hand_image_url],
                style_by_url.get(pair.style_image_url, ""),
                pair.hand_image_url,
                pair.style_image_url,
                now,
            ),
        )

    _seed_ugc_keywords(conn, now)


def _seed_style_tags(conn: sqlite3.Connection, style_id: str, now: str) -> None:
    tags = _seed_tags_for_style(style_id)
    for tag_type, values in tags.items():
        for value in values:
            conn.execute(
                """
                INSERT OR IGNORE INTO style_tags
                (style_id, tag_type, tag_value, source, created_at)
                VALUES (?, ?, ?, 'seed_or_mock', ?)
                """,
                (style_id, tag_type, value, now),
            )


def _seed_style_signals(conn: sqlite3.Connection, style_id: str, now: str) -> None:
    suffix = int(style_id[-3:])
    signals = [
        ("搜索热度", 60 + suffix % 30, 0.08 + (suffix % 5) * 0.03, 0.30),
        ("UGC词频", 80 + suffix * 3, 0.05 + (suffix % 4) * 0.02, 0.30),
        ("试戴收藏率", 0.20 + (suffix % 8) * 0.03, 0.06 + (suffix % 3) * 0.04, 0.40),
    ]
    for signal, value, delta, weight in signals:
        conn.execute(
            """
            INSERT OR REPLACE INTO style_signals
            (style_id, signal, value, delta, weight, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (style_id, signal, value, delta, weight, now),
        )


def _seed_ugc_keywords(conn: sqlite3.Connection, now: str) -> None:
    keywords = [
        ("奶油猫眼", 92, 0.31, ["猫眼", "奶油白", "显白"]),
        ("法式简约", 86, 0.18, ["法式", "通勤", "简约"]),
        ("圣诞美甲", 78, 0.24, ["节日", "红色", "镜面"]),
        ("显白美甲", 88, 0.21, ["显白", "豆沙粉", "玫瑰金"]),
    ]
    for keyword, heat_score, delta, tags in keywords:
        conn.execute(
            """
            INSERT OR REPLACE INTO ugc_keywords
            (keyword, heat_score, delta, related_tags_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (keyword, heat_score, delta, json.dumps(tags, ensure_ascii=False), now),
        )


def _seed_tags_for_style(style_id: str) -> dict[str, list[str]]:
    suffix = int(style_id[-3:])
    palettes = [
        {
            "color_system": ["裸色系", "粉色系"],
            "style_tags": ["甜美", "温柔"],
            "scene_tags": ["约会", "日常通勤"],
            "season_tags": ["秋", "冬"],
            "skin_tone_suitability": ["冷白皮", "自然肤色"],
            "nail_technique": ["猫眼", "渐变"],
            "nail_decoration": ["碎钻/小钻"],
            "nail_finish": ["亮面"],
            "nail_shape": ["杏仁形"],
            "nail_length": ["中甲"],
            "finger_shape": ["修长"],
            "nail_bed_shape": ["标准甲床"],
        },
        {
            "color_system": ["裸色系"],
            "style_tags": ["法式", "简约", "百搭"],
            "scene_tags": ["日常通勤", "职场"],
            "season_tags": ["四季通用"],
            "skin_tone_suitability": ["全肤色通用"],
            "nail_technique": ["法式", "纯色"],
            "nail_decoration": ["无装饰"],
            "nail_finish": ["亮面"],
            "nail_shape": ["方圆形"],
            "nail_length": ["短甲"],
            "finger_shape": ["标准"],
            "nail_bed_shape": ["标准甲床"],
        },
        {
            "color_system": ["红色系", "金色系"],
            "style_tags": ["个性", "时尚"],
            "scene_tags": ["派对/夜店"],
            "season_tags": ["圣诞", "冬"],
            "skin_tone_suitability": ["深肤色", "暖黄皮"],
            "nail_technique": ["镜面"],
            "nail_decoration": ["金属箔/金线"],
            "nail_finish": ["镜面光"],
            "nail_shape": ["方圆形"],
            "nail_length": ["中甲"],
            "finger_shape": ["标准"],
            "nail_bed_shape": ["宽甲床"],
        },
        {
            "color_system": ["蓝色系", "银色系"],
            "style_tags": ["酷飒", "个性"],
            "scene_tags": ["约会", "度假"],
            "season_tags": ["夏"],
            "skin_tone_suitability": ["冷白皮"],
            "nail_technique": ["渐变", "镭射/极光"],
            "nail_decoration": ["亮片/闪粉"],
            "nail_finish": ["猫眼光"],
            "nail_shape": ["椭圆形"],
            "nail_length": ["长甲"],
            "finger_shape": ["修长"],
            "nail_bed_shape": ["窄甲床"],
        },
    ]
    return palettes[(suffix - 1) % len(palettes)]


def _merge_tags(seed_tags: dict[str, list[str]], tag_rows: list[sqlite3.Row]) -> dict[str, list[str]]:
    merged: dict[str, set[str]] = {key: set(values) for key, values in seed_tags.items()}
    for row in tag_rows:
        merged.setdefault(row["tag_type"], set()).add(row["tag_value"])
    return {key: sorted(values) for key, values in merged.items()}


def _seed_hot_score(style_id: str) -> float:
    suffix = int(style_id[-3:])
    return float(55 + (suffix * 7) % 40)


def _seed_life_cycle(style_id: str) -> str:
    suffix = int(style_id[-3:])
    return ["上升期", "峰值期", "观察期", "衰退期"][suffix % 4]


def _count_rows(conn: sqlite3.Connection, table: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
    return int(row["count"])


def _database_path() -> Path:
    path = Path(get_settings().database_path)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / path
    return path


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _event_stats_for_style(conn: sqlite3.Connection, style_id: str) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT event_type, COUNT(*) AS count
        FROM user_events
        WHERE style_id = ?
        GROUP BY event_type
        """,
        (style_id,),
    ).fetchall()
    return {row["event_type"]: int(row["count"]) for row in rows}


def _push_id_for_style(style_id: str) -> str:
    return "push-" + style_id.replace("style-", "")
