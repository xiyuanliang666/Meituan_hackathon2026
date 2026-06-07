import json
import sqlite3
from uuid import uuid4
from contextlib import contextmanager
from datetime import datetime, timezone
UTC = timezone.utc
from pathlib import Path
from typing import Any, Iterator

from app.config import get_settings
from app.data.nail_taxonomy_v2_seed import STYLE_TAG_FIELD_KEYS, TAXONOMY_V2_OPTIONS
from app.services.dataset_loader import load_evaluation_dataset
from app.services.image_storage import mirror_remote_image


@contextmanager
def connect_db() -> Iterator[sqlite3.Connection]:
    path = _database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        if connection.in_transaction:
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
        "merchant_template_selections",
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
        "user_hand_assets",
        "user_hand_profiles",
        "user_recommendation_snapshots",
        "user_tune_history",
        "user_demo_state",
        "ugc_posts",
        "trend_runs",
        "trends",
        "merchant_trend_actions",
        "candidate_taxonomy_terms",
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
                   status, review_status, source, material_status, source_trend_id, created_at
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


def find_style_id_by_image_url(image_url: str) -> str | None:
    init_db(seed=True)
    with connect_db() as conn:
        row = conn.execute(
            """
            SELECT style_id
            FROM styles
            WHERE enhanced_style_image_url = ? OR original_style_image_url = ?
            LIMIT 1
            """,
            (image_url, image_url),
        ).fetchone()
    return str(row["style_id"]) if row else None


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


def list_user_hand_assets(user_id: str) -> list[dict[str, Any]]:
    init_db(seed=True)
    with connect_db() as conn:
        rows = conn.execute(
            """
            SELECT user_id, hand_id, image_url, selected, quality_pass, quality_issues_json,
                   nail_art_detected, processing_note, created_at, updated_at
            FROM user_hand_assets
            WHERE user_id = ?
            ORDER BY selected DESC, updated_at DESC, created_at DESC
            """,
            (user_id,),
        ).fetchall()
    return [_user_hand_asset_payload(dict(row)) for row in rows]


def get_user_hand_asset(hand_id: str, user_id: str | None = None) -> dict[str, Any] | None:
    init_db(seed=True)
    with connect_db() as conn:
        if user_id:
            row = conn.execute(
                """
                SELECT user_id, hand_id, image_url, selected, quality_pass, quality_issues_json,
                       nail_art_detected, processing_note, created_at, updated_at
                FROM user_hand_assets
                WHERE user_id = ? AND hand_id = ?
                """,
                (user_id, hand_id),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT user_id, hand_id, image_url, selected, quality_pass, quality_issues_json,
                       nail_art_detected, processing_note, created_at, updated_at
                FROM user_hand_assets
                WHERE hand_id = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (hand_id,),
            ).fetchone()
    return _user_hand_asset_payload(dict(row)) if row else None


def get_user_hand_asset_by_image(user_id: str, image_url: str) -> dict[str, Any] | None:
    init_db(seed=True)
    with connect_db() as conn:
        row = conn.execute(
            """
            SELECT user_id, hand_id, image_url, selected, quality_pass, quality_issues_json,
                   nail_art_detected, processing_note, created_at, updated_at
            FROM user_hand_assets
            WHERE user_id = ? AND image_url = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (user_id, image_url),
        ).fetchone()
    return _user_hand_asset_payload(dict(row)) if row else None


def get_selected_user_hand_asset(user_id: str) -> dict[str, Any] | None:
    hands = list_user_hand_assets(user_id)
    return hands[0] if hands else None


def save_user_hand_asset(
    user_id: str,
    hand_id: str,
    image_url: str,
    *,
    selected: bool,
    quality_pass: bool,
    quality_issues: list[str] | None = None,
    nail_art_detected: bool = False,
    processing_note: str = "",
) -> dict[str, Any]:
    init_db(seed=True)
    now = _now()
    issues_json = json.dumps(quality_issues or [], ensure_ascii=False)
    with connect_db() as conn:
        if selected:
            conn.execute("UPDATE user_hand_assets SET selected = 0, updated_at = ? WHERE user_id = ?", (now, user_id))
        conn.execute(
            """
            INSERT INTO user_hand_assets
            (user_id, hand_id, image_url, selected, quality_pass, quality_issues_json,
             nail_art_detected, processing_note, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, hand_id) DO UPDATE SET
                image_url = excluded.image_url,
                selected = excluded.selected,
                quality_pass = excluded.quality_pass,
                quality_issues_json = excluded.quality_issues_json,
                nail_art_detected = excluded.nail_art_detected,
                processing_note = excluded.processing_note,
                updated_at = excluded.updated_at
            """,
            (
                user_id,
                hand_id,
                image_url,
                1 if selected else 0,
                1 if quality_pass else 0,
                issues_json,
                1 if nail_art_detected else 0,
                processing_note,
                now,
                now,
            ),
        )
        row = conn.execute(
            """
            SELECT user_id, hand_id, image_url, selected, quality_pass, quality_issues_json,
                   nail_art_detected, processing_note, created_at, updated_at
            FROM user_hand_assets
            WHERE user_id = ? AND hand_id = ?
            """,
            (user_id, hand_id),
        ).fetchone()
    return _user_hand_asset_payload(dict(row))


def sync_user_hand_assets(user_id: str, hands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    init_db(seed=True)
    if not hands:
        with connect_db() as conn:
            conn.execute("DELETE FROM user_hand_assets WHERE user_id = ?", (user_id,))
        return []

    existing = {item["hand_id"]: item for item in list_user_hand_assets(user_id)}
    selected_hand_id = next((item["hand_id"] for item in hands if item.get("selected")), hands[0]["hand_id"])
    synced: list[dict[str, Any]] = []
    for item in hands:
        prev = existing.get(item["hand_id"], {})
        synced.append(
            save_user_hand_asset(
                user_id=user_id,
                hand_id=item["hand_id"],
                image_url=item["image_url"],
                selected=item["hand_id"] == selected_hand_id,
                quality_pass=bool(prev.get("quality_pass", True)),
                quality_issues=prev.get("quality_issues", []),
                nail_art_detected=bool(prev.get("nail_art_detected", False)),
                processing_note=str(prev.get("processing_note") or ""),
            )
        )
    return synced


def get_user_hand_profile(hand_profile_id: str) -> dict[str, Any] | None:
    init_db(seed=True)
    with connect_db() as conn:
        row = conn.execute(
            """
            SELECT hand_profile_id, user_id, hand_id, hand_image_url, skin_tone, hand_shape,
                   recommended_colors_json, recommended_styles_json, recommended_nail_shapes_json,
                   analysis_reason, analysis_mode, created_at
            FROM user_hand_profiles
            WHERE hand_profile_id = ?
            """,
            (hand_profile_id,),
        ).fetchone()
    return _user_hand_profile_payload(dict(row)) if row else None


def find_user_hand_profile(user_id: str | None, hand_image_url: str, hand_profile_id: str | None = None) -> dict[str, Any] | None:
    init_db(seed=True)
    with connect_db() as conn:
        row = None
        if user_id:
            row = conn.execute(
                """
                SELECT hand_profile_id, user_id, hand_id, hand_image_url, skin_tone, hand_shape,
                       recommended_colors_json, recommended_styles_json, recommended_nail_shapes_json,
                       analysis_reason, analysis_mode, created_at
                FROM user_hand_profiles
                WHERE user_id = ? AND hand_image_url = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (user_id, hand_image_url),
            ).fetchone()
        if row is None and hand_profile_id:
            row = conn.execute(
                """
                SELECT hand_profile_id, user_id, hand_id, hand_image_url, skin_tone, hand_shape,
                       recommended_colors_json, recommended_styles_json, recommended_nail_shapes_json,
                       analysis_reason, analysis_mode, created_at
                FROM user_hand_profiles
                WHERE hand_profile_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (hand_profile_id,),
            ).fetchone()
    return _user_hand_profile_payload(dict(row)) if row else None


def save_user_hand_profile(
    *,
    hand_profile_id: str,
    user_id: str | None,
    hand_id: str | None,
    hand_image_url: str,
    skin_tone: str,
    hand_shape: str,
    recommended_colors: list[str],
    recommended_styles: list[str],
    recommended_nail_shapes: list[str],
    analysis_reason: str,
    analysis_mode: str,
) -> dict[str, Any]:
    init_db(seed=True)
    now = _now()
    with connect_db() as conn:
        conn.execute(
            """
            INSERT INTO user_hand_profiles
            (hand_profile_id, user_id, hand_id, hand_image_url, skin_tone, hand_shape,
             recommended_colors_json, recommended_styles_json, recommended_nail_shapes_json,
             analysis_reason, analysis_mode, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(hand_profile_id) DO UPDATE SET
                user_id = excluded.user_id,
                hand_id = COALESCE(excluded.hand_id, user_hand_profiles.hand_id),
                hand_image_url = excluded.hand_image_url,
                skin_tone = excluded.skin_tone,
                hand_shape = excluded.hand_shape,
                recommended_colors_json = excluded.recommended_colors_json,
                recommended_styles_json = excluded.recommended_styles_json,
                recommended_nail_shapes_json = excluded.recommended_nail_shapes_json,
                analysis_reason = excluded.analysis_reason,
                analysis_mode = excluded.analysis_mode
            """,
            (
                hand_profile_id,
                user_id,
                hand_id,
                hand_image_url,
                skin_tone,
                hand_shape,
                json.dumps(recommended_colors, ensure_ascii=False),
                json.dumps(recommended_styles, ensure_ascii=False),
                json.dumps(recommended_nail_shapes, ensure_ascii=False),
                analysis_reason,
                analysis_mode,
                now,
            ),
        )
        row = conn.execute(
            """
            SELECT hand_profile_id, user_id, hand_id, hand_image_url, skin_tone, hand_shape,
                   recommended_colors_json, recommended_styles_json, recommended_nail_shapes_json,
                   analysis_reason, analysis_mode, created_at
            FROM user_hand_profiles
            WHERE hand_profile_id = ?
            """,
            (hand_profile_id,),
        ).fetchone()
    return _user_hand_profile_payload(dict(row))


def save_recommendation_snapshot(
    *,
    user_id: str,
    hand_profile_id: str,
    query: str | None,
    recommendations: list[dict[str, Any]],
) -> dict[str, Any]:
    init_db(seed=True)
    snapshot_id = "rec-" + uuid4().hex[:12]
    created_at = _now()
    with connect_db() as conn:
        conn.execute(
            """
            INSERT INTO user_recommendation_snapshots
            (snapshot_id, user_id, hand_profile_id, query, recommendations_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                user_id,
                hand_profile_id,
                query or "",
                json.dumps(recommendations, ensure_ascii=False),
                created_at,
            ),
        )
        row = conn.execute(
            """
            SELECT snapshot_id, user_id, hand_profile_id, query, recommendations_json, created_at
            FROM user_recommendation_snapshots
            WHERE snapshot_id = ?
            """,
            (snapshot_id,),
        ).fetchone()
    return _recommendation_snapshot_payload(dict(row))


def get_recommendation_snapshot(snapshot_id: str) -> dict[str, Any] | None:
    init_db(seed=True)
    with connect_db() as conn:
        row = conn.execute(
            """
            SELECT snapshot_id, user_id, hand_profile_id, query, recommendations_json, created_at
            FROM user_recommendation_snapshots
            WHERE snapshot_id = ?
            """,
            (snapshot_id,),
        ).fetchone()
    return _recommendation_snapshot_payload(dict(row)) if row else None


def get_latest_recommendation_snapshot(user_id: str, hand_profile_id: str | None = None) -> dict[str, Any] | None:
    init_db(seed=True)
    with connect_db() as conn:
        if hand_profile_id:
            row = conn.execute(
                """
                SELECT snapshot_id, user_id, hand_profile_id, query, recommendations_json, created_at
                FROM user_recommendation_snapshots
                WHERE user_id = ? AND hand_profile_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (user_id, hand_profile_id),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT snapshot_id, user_id, hand_profile_id, query, recommendations_json, created_at
                FROM user_recommendation_snapshots
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
    return _recommendation_snapshot_payload(dict(row)) if row else None


def save_user_tune_history(
    *,
    user_id: str,
    source_style_id: str | None,
    source_style_image_url: str,
    tuned_image_url: str,
    nail_shape_id: str | None,
    color: str | None,
    user_text: str | None,
    generation_mode: str,
) -> dict[str, Any]:
    init_db(seed=True)
    tune_id = "tune-" + uuid4().hex[:12]
    created_at = _now()
    with connect_db() as conn:
        conn.execute(
            """
            INSERT INTO user_tune_history
            (tune_id, user_id, source_style_id, source_style_image_url, tuned_image_url,
             nail_shape_id, color, user_text, generation_mode, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tune_id,
                user_id,
                source_style_id,
                source_style_image_url,
                tuned_image_url,
                nail_shape_id,
                color,
                user_text,
                generation_mode,
                created_at,
            ),
        )
        row = conn.execute(
            """
            SELECT tune_id, user_id, source_style_id, source_style_image_url, tuned_image_url,
                   nail_shape_id, color, user_text, generation_mode, created_at
            FROM user_tune_history
            WHERE tune_id = ?
            """,
            (tune_id,),
        ).fetchone()
    return dict(row) if row else {}


def get_user_tune_history_item(tune_id: str) -> dict[str, Any] | None:
    init_db(seed=True)
    with connect_db() as conn:
        row = conn.execute(
            """
            SELECT tune_id, user_id, source_style_id, source_style_image_url, tuned_image_url,
                   nail_shape_id, color, user_text, generation_mode, created_at
            FROM user_tune_history
            WHERE tune_id = ?
            """,
            (tune_id,),
        ).fetchone()
    return dict(row) if row else None


def get_latest_user_tune(user_id: str, source_style_id: str | None = None) -> dict[str, Any] | None:
    init_db(seed=True)
    with connect_db() as conn:
        if source_style_id:
            row = conn.execute(
                """
                SELECT tune_id, user_id, source_style_id, source_style_image_url, tuned_image_url,
                       nail_shape_id, color, user_text, generation_mode, created_at
                FROM user_tune_history
                WHERE user_id = ? AND source_style_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (user_id, source_style_id),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT tune_id, user_id, source_style_id, source_style_image_url, tuned_image_url,
                       nail_shape_id, color, user_text, generation_mode, created_at
                FROM user_tune_history
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
    return dict(row) if row else None


def get_user_demo_state(user_id: str) -> dict[str, Any] | None:
    init_db(seed=True)
    with connect_db() as conn:
        row = conn.execute(
            """
            SELECT user_id, current_hand_id, current_hand_profile_id,
                   current_recommendation_snapshot_id, current_tune_id, updated_at
            FROM user_demo_state
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
    return dict(row) if row else None


def upsert_user_demo_state(
    user_id: str,
    *,
    current_hand_id: str | None = None,
    current_hand_profile_id: str | None = None,
    current_recommendation_snapshot_id: str | None = None,
    current_tune_id: str | None = None,
) -> dict[str, Any]:
    init_db(seed=True)
    now = _now()
    existing = get_user_demo_state(user_id) or {
        "user_id": user_id,
        "current_hand_id": None,
        "current_hand_profile_id": None,
        "current_recommendation_snapshot_id": None,
        "current_tune_id": None,
        "updated_at": now,
    }
    payload = {
        "current_hand_id": existing.get("current_hand_id"),
        "current_hand_profile_id": existing.get("current_hand_profile_id"),
        "current_recommendation_snapshot_id": existing.get("current_recommendation_snapshot_id"),
        "current_tune_id": existing.get("current_tune_id"),
    }
    updates = {
        "current_hand_id": current_hand_id,
        "current_hand_profile_id": current_hand_profile_id,
        "current_recommendation_snapshot_id": current_recommendation_snapshot_id,
        "current_tune_id": current_tune_id,
    }
    for key, value in updates.items():
        if value is not None:
            payload[key] = value
    with connect_db() as conn:
        conn.execute(
            """
            INSERT INTO user_demo_state
            (user_id, current_hand_id, current_hand_profile_id,
             current_recommendation_snapshot_id, current_tune_id, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                current_hand_id = excluded.current_hand_id,
                current_hand_profile_id = excluded.current_hand_profile_id,
                current_recommendation_snapshot_id = excluded.current_recommendation_snapshot_id,
                current_tune_id = excluded.current_tune_id,
                updated_at = excluded.updated_at
            """,
            (
                user_id,
                payload["current_hand_id"],
                payload["current_hand_profile_id"],
                payload["current_recommendation_snapshot_id"],
                payload["current_tune_id"],
                now,
            ),
        )
        row = conn.execute(
            """
            SELECT user_id, current_hand_id, current_hand_profile_id,
                   current_recommendation_snapshot_id, current_tune_id, updated_at
            FROM user_demo_state
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
    return dict(row) if row else payload


def clear_user_demo_data(user_id: str) -> None:
    init_db(seed=True)
    with connect_db() as conn:
        conn.execute("DELETE FROM user_tryon_history WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM user_tune_history WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM user_recommendation_snapshots WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM user_hand_profiles WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM user_hand_assets WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM user_demo_state WHERE user_id = ?", (user_id,))


def list_hot_push_candidates(limit: int = 10) -> list[dict[str, Any]]:
    with connect_db() as conn:
        _create_tables(conn)
        rows = conn.execute(
            """
            SELECT push_id, style_id, merchant_id, status, selected_image_url,
                   selected_coupon_url, final_tagline, final_price, updated_at,
                   snapshot_style_name, snapshot_image_url, snapshot_tags_json,
                   snapshot_hot_score, snapshot_life_cycle, snapshot_signals_json,
                   snapshot_source_posts_json, snapshot_image_urls_json
            FROM push_audits
            WHERE status != 'rejected'
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        candidates: list[dict[str, Any]] = []
        for row in rows:
            audit = dict(row)
            snapshot = _push_snapshot_from_audit(conn, audit)
            candidates.append(
                {
                    "push_id": audit["push_id"],
                    "style_id": audit["style_id"],
                    "style_name": snapshot["style_name"],
                    "enhanced_style_image_url": snapshot["image_url"],
                    "hot_score": snapshot["hot_score"],
                    "life_cycle": snapshot["life_cycle"],
                    "tags": snapshot["tags"],
                    "signals": snapshot["signals"],
                    "source_posts": snapshot.get("source_posts", []),
                    "style_image_urls": snapshot.get("style_image_urls", []),
                    "event_stats": _event_stats_for_style(conn, audit["style_id"]) if audit["style_id"] else {},
                    "status": audit["status"],
                    "audit_details": audit,
                }
            )
    return candidates


def set_pending_push_styles(
    style_ids: list[str],
    merchant_id: str = "demo_shop",
    replace_pending: bool = False,
) -> dict[str, Any]:
    unique_style_ids = list(dict.fromkeys(style_ids))
    now = _now()
    with connect_db() as conn:
        _create_tables(conn)
        rows = conn.execute(
            f"""
            SELECT style_id, style_name, enhanced_style_image_url, tags_json, hot_score, life_cycle
            FROM styles
            WHERE style_id IN ({','.join('?' for _ in unique_style_ids) if unique_style_ids else "''"})
              AND COALESCE(status, 'active') != 'deleted'
            """,
            unique_style_ids,
        ).fetchall()
        found = {row["style_id"]: dict(row) for row in rows}
        missing = [style_id for style_id in unique_style_ids if style_id not in found]

        if replace_pending:
            conn.execute(
                """
                UPDATE push_audits
                SET status = 'rejected', updated_at = ?
                WHERE status NOT IN ('published', 'accepted', 'listed')
                """,
                (now,),
            )

        for style_id in found:
            push_id = _push_id_for_style(style_id)
            snapshot = _build_push_snapshot(conn, style_id, found[style_id])
            conn.execute(
                """
                INSERT INTO push_audits
                (push_id, style_id, merchant_id, status, selected_image_url, selected_coupon_url,
                 final_tagline, final_price, updated_at, snapshot_style_name, snapshot_image_url,
                 snapshot_tags_json, snapshot_hot_score, snapshot_life_cycle, snapshot_signals_json)
                VALUES (?, ?, ?, 'pending', NULL, NULL, NULL, NULL, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(push_id) DO UPDATE SET
                    merchant_id = excluded.merchant_id,
                    status = 'pending',
                    selected_image_url = NULL,
                    selected_coupon_url = NULL,
                    final_tagline = NULL,
                    final_price = NULL,
                    updated_at = excluded.updated_at,
                    snapshot_style_name = excluded.snapshot_style_name,
                    snapshot_image_url = excluded.snapshot_image_url,
                    snapshot_tags_json = excluded.snapshot_tags_json,
                    snapshot_hot_score = excluded.snapshot_hot_score,
                    snapshot_life_cycle = excluded.snapshot_life_cycle,
                    snapshot_signals_json = excluded.snapshot_signals_json
                """,
                (
                    push_id,
                    style_id,
                    merchant_id,
                    now,
                    snapshot["style_name"],
                    snapshot["image_url"],
                    json.dumps(snapshot["tags"], ensure_ascii=False),
                    snapshot["hot_score"],
                    snapshot["life_cycle"],
                    json.dumps(snapshot["signals"], ensure_ascii=False),
                ),
            )

        pending_rows = conn.execute(
            """
            SELECT push_id, style_id, status
            FROM push_audits
            WHERE status = 'pending'
            ORDER BY updated_at DESC
            """
        ).fetchall()
    return {
        "requested_style_ids": unique_style_ids,
        "missing_style_ids": missing,
        "pending": [dict(row) for row in pending_rows],
    }


def set_pending_push_trends(
    trend_ids: list[str],
    merchant_id: str = "demo_shop",
) -> dict[str, Any]:
    """将趋势发现中 promote 的趋势写入 push_audits，进入待上架队列。"""
    unique_trend_ids = list(dict.fromkeys(trend_ids))
    now = _now()
    with connect_db() as conn:
        _create_tables(conn)
        found: dict[str, dict[str, Any]] = {}
        missing: list[str] = []
        for trend_id in unique_trend_ids:
            row = conn.execute(
                "SELECT * FROM trends WHERE trend_id = ?",
                (trend_id,),
            ).fetchone()
            if row:
                found[trend_id] = _trend_payload(dict(row))
            else:
                missing.append(trend_id)
        trend_score_max = float(
            conn.execute("SELECT MAX(trend_score) AS max_score FROM trends").fetchone()["max_score"] or 0.0
        )

    prepared = [
        _trend_push_snapshot(
            trend_id=trend_id,
            trend=trend,
            merchant_id=merchant_id,
            trend_score_max=trend_score_max,
        )
        for trend_id, trend in found.items()
    ]

    with connect_db() as conn:
        _create_tables(conn)
        for item in prepared:
            snapshot = item["snapshot"]
            conn.execute(
                """
                INSERT INTO push_audits
                (push_id, style_id, merchant_id, status, selected_image_url, selected_coupon_url,
                 final_tagline, final_price, updated_at, snapshot_style_name, snapshot_image_url,
                 snapshot_tags_json, snapshot_hot_score, snapshot_life_cycle, snapshot_signals_json,
                 snapshot_source_posts_json, snapshot_image_urls_json)
                VALUES (?, ?, ?, 'pending', NULL, NULL, NULL, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(push_id) DO UPDATE SET
                    merchant_id = excluded.merchant_id,
                    status = 'pending',
                    selected_image_url = NULL,
                    selected_coupon_url = NULL,
                    final_tagline = NULL,
                    final_price = NULL,
                    updated_at = excluded.updated_at,
                    snapshot_style_name = excluded.snapshot_style_name,
                    snapshot_image_url = excluded.snapshot_image_url,
                    snapshot_tags_json = excluded.snapshot_tags_json,
                    snapshot_hot_score = excluded.snapshot_hot_score,
                    snapshot_life_cycle = excluded.snapshot_life_cycle,
                    snapshot_signals_json = excluded.snapshot_signals_json,
                    snapshot_source_posts_json = excluded.snapshot_source_posts_json,
                    snapshot_image_urls_json = excluded.snapshot_image_urls_json
                """,
                (
                    item["push_id"],
                    "",
                    merchant_id,
                    now,
                    snapshot["style_name"],
                    snapshot["image_url"],
                    json.dumps(snapshot["tags"], ensure_ascii=False),
                    snapshot["hot_score"],
                    snapshot["life_cycle"],
                    json.dumps(snapshot["signals"], ensure_ascii=False),
                    json.dumps(snapshot["source_posts"], ensure_ascii=False),
                    json.dumps(snapshot["style_image_urls"], ensure_ascii=False),
                ),
            )

        pending_rows = conn.execute(
            """
            SELECT push_id, style_id, status
            FROM push_audits
            WHERE status = 'pending'
            ORDER BY updated_at DESC
            """
        ).fetchall()
    return {
        "requested_trend_ids": unique_trend_ids,
        "missing_trend_ids": missing,
        "pending": [dict(row) for row in pending_rows],
    }


def _trend_push_snapshot(
    trend_id: str,
    trend: dict[str, Any],
    merchant_id: str,
    trend_score_max: float = 0.0,
) -> dict[str, Any]:
    push_id = _push_id_for_trend(trend_id)
    source_posts = _trend_source_posts(trend)
    representative_image_url = _representative_post_image(trend, source_posts)
    metrics = trend.get("metrics") if isinstance(trend.get("metrics"), dict) else {}
    comment_summary = trend.get("comment_signal_summary") if isinstance(trend.get("comment_signal_summary"), dict) else {}

    trend_score = float(trend.get("trend_score") or 0.0)
    trend_score_display = _trend_display_score(trend_score, trend_score_max)
    velocity_score = float(metrics.get("velocity_score") or metrics.get("velocity") or 0.0)
    support_post_count = int(metrics.get("support_post_count") or len(source_posts) or 0)

    search_heat = round(
        min(100.0, 35 + trend_score_display * 0.45 + velocity_score * 12 + support_post_count * 1.2),
        1,
    )
    demand_total = _signal_count_total(comment_summary, ("demand_signals", "user_demands", "purchase_intents"))
    social_total = _signal_count_total(comment_summary, ("social_proof_signals", "social_proofs"))
    comment_total = sum(int(post.get("metrics", {}).get("comments") or 0) for post in source_posts)
    review_frequency = int(round(comment_total * 0.18 + demand_total * 6 + social_total * 4))
    favorite_rate = _stable_mock_rate(push_id, min_rate=0.20, max_rate=0.50)

    signals = [
        {
            "signal": "搜索热度",
            "value": search_heat,
            "delta": round(min(0.45, max(0.08, velocity_score * 0.12)), 2),
            "weight": 0.34,
        },
        {
            "signal": "评价词频",
            "value": review_frequency,
            "delta": round(min(0.35, max(0.06, (demand_total + social_total) / max(review_frequency, 1))), 2),
            "weight": 0.32,
        },
        {
            "signal": "试戴收藏率",
            "value": favorite_rate,
            "delta": _stable_mock_rate(f"{push_id}:delta", min_rate=0.10, max_rate=0.25),
            "weight": 0.34,
        },
    ]

    tags = _trend_push_tags(trend)
    style_image_urls = [representative_image_url] if representative_image_url else []
    style_image_urls.extend(_generate_trend_push_composites(push_id, representative_image_url, merchant_id))

    return {
        "push_id": push_id,
        "snapshot": {
            "style_name": trend.get("core_style") or "趋势爆款",
            "image_url": representative_image_url,
            "tags": tags,
            "hot_score": trend_score_display,
            "life_cycle": trend.get("life_cycle") or "观察期",
            "signals": signals,
            "source_posts": source_posts,
            "style_image_urls": style_image_urls,
        },
    }


def _trend_display_score(trend_score: float, trend_score_max: float) -> float:
    if trend_score <= 0:
        return 0.0
    if trend_score_max <= 0:
        return round(min(93.8, trend_score), 1)
    return round(min(93.8, trend_score / trend_score_max * 93.8), 1)


def _trend_push_tags(trend: dict[str, Any]) -> dict[str, Any]:
    try:
        from app.data.nail_taxonomy_v2_seed import ARRAY_FIELD_KEYS
        from app.services.taxonomy_store import get_approved_values_map

        approved = get_approved_values_map()
        metrics = trend.get("metrics") if isinstance(trend.get("metrics"), dict) else {}
        candidates: list[str] = []
        for value in trend.get("keywords") or []:
            text = str(value).strip()
            if text:
                candidates.append(text)
        for value in metrics.get("core_style_tags") or []:
            text = str(value).strip()
            if text:
                candidates.append(text)
        core_style = str(trend.get("core_style") or "").strip()
        if core_style:
            candidates.append(core_style)

        deduped = list(dict.fromkeys(candidates))
        tags: dict[str, list[str]] = {field_key: [] for field_key in ARRAY_FIELD_KEYS}
        matched: set[str] = set()
        for field_key in ARRAY_FIELD_KEYS:
            allowed = approved.get(field_key, set())
            values = [value for value in deduped if value in allowed]
            if values:
                tags[field_key] = values
                matched.update(values)
        unmatched = [value for value in deduped if value not in matched]
        if unmatched:
            tags["candidate_tags"] = unmatched[:8]
        if any(tags.values()):
            return tags
    except Exception:
        pass

    keywords = trend.get("keywords") or []
    return {"style_tags": list(keywords)[:8]} if isinstance(keywords, list) and keywords else {}


def _trend_source_posts(trend: dict[str, Any]) -> list[dict[str, Any]]:
    posts = trend.get("supporting_posts") if isinstance(trend.get("supporting_posts"), list) else []
    normalized = [_normalize_trend_source_post(item) for item in posts if isinstance(item, dict)]
    normalized.sort(key=_source_post_rank, reverse=True)
    return normalized


def _normalize_trend_source_post(post: dict[str, Any]) -> dict[str, Any]:
    metrics = post.get("metrics") if isinstance(post.get("metrics"), dict) else {}
    likes = int(post.get("like_count") or metrics.get("likes") or metrics.get("like_count") or 0)
    favorites = int(post.get("favorite_count") or metrics.get("favorites") or metrics.get("favorite_count") or 0)
    comments = int(post.get("comment_count") or metrics.get("comments") or metrics.get("comment_count") or 0)
    image_urls = post.get("image_urls") if isinstance(post.get("image_urls"), list) else []
    comment_insights = post.get("comment_insights") if isinstance(post.get("comment_insights"), dict) else {}
    return {
        "post_id": post.get("post_id") or "",
        "title": post.get("title") or post.get("content") or "趋势来源帖",
        "summary": post.get("summary") or comment_insights.get("summary") or comment_insights.get("comment_summary") or "",
        "image_url": (
            post.get("image_url")
            or post.get("representative_image_url")
            or post.get("cover_image_url")
            or (image_urls[0] if image_urls else "")
        ),
        "url": post.get("source_url") or post.get("url") or "",
        "platform": post.get("source") or "小红书",
        "relative_time": post.get("relative_time") or "",
        "metrics": {
            "likes": likes,
            "favorites": favorites,
            "comments": comments,
            "growth_3d": int(round(float(post.get("growth_3d") or metrics.get("growth_3d") or 0))),
        },
        "status": {"label": "趋势支撑"},
    }


def _source_post_rank(post: dict[str, Any]) -> float:
    metrics = post.get("metrics") if isinstance(post.get("metrics"), dict) else {}
    return (
        float(metrics.get("likes") or 0) * 1.0
        + float(metrics.get("favorites") or 0) * 1.4
        + float(metrics.get("comments") or 0) * 1.8
    )


def _representative_post_image(trend: dict[str, Any], source_posts: list[dict[str, Any]]) -> str:
    for post in source_posts:
        image_url = str(post.get("image_url") or "").strip()
        if image_url:
            return image_url
    return str(trend.get("representative_image_url") or trend.get("style_source_image_url") or "").strip()


def _signal_count_total(summary: dict[str, Any], keys: tuple[str, ...]) -> int:
    total = 0
    for key in keys:
        values = summary.get(key)
        if isinstance(values, dict):
            total += sum(int(value or 0) for value in values.values())
        elif isinstance(values, list):
            for item in values:
                if isinstance(item, dict):
                    total += int(item.get("count") or item.get("value") or 1)
                elif item:
                    total += 1
    return total


def _stable_mock_rate(seed: str, min_rate: float, max_rate: float) -> float:
    span = max_rate - min_rate
    if span <= 0:
        return round(min_rate, 2)
    seed_value = sum((index + 1) * ord(ch) for index, ch in enumerate(seed))
    return round(min_rate + (seed_value % 1000) / 999 * span, 2)


def _generate_trend_push_composites(push_id: str, style_image_url: str, merchant_id: str) -> list[str]:
    if not style_image_url:
        return []
    output: list[str] = []
    for template_id in list_selected_template_ids(merchant_id)[:4]:
        template = get_template_by_id(template_id)
        template_image_url = str((template or {}).get("hand_image_url") or "").strip()
        if not template_image_url:
            continue
        try:
            from app.schemas.style import CompositeRequest
            from app.services.image_generation import generate_composite_image

            generated = generate_composite_image(
                CompositeRequest(
                    style_image_url=style_image_url,
                    template_image_url=template_image_url,
                )
            )
            if generated.composite_image_url:
                output.append(generated.composite_image_url)
        except Exception:
            continue
    return output


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
    now = _now()
    with connect_db() as conn:
        _create_tables(conn)
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


def update_push_composites(push_id: str, image_urls: list[str]) -> bool:
    """持久化推送卡片的合成图 URL 列表到 snapshot_image_urls_json。"""
    now_str = _now()
    with connect_db() as conn:
        _create_tables(conn)
        cur = conn.execute(
            "UPDATE push_audits SET snapshot_image_urls_json = ?, updated_at = ? WHERE push_id = ?",
            (json.dumps(image_urls, ensure_ascii=False), now_str, push_id),
        )
        return cur.rowcount > 0


def update_push_draft(
    push_id: str,
    selected_image_url: str | None = None,
    selected_coupon_url: str | None = None,
    final_tagline: str | None = None,
    final_price: float | None = None,
) -> bool:
    """Update push editor draft fields without changing status."""
    now_str = _now()
    with connect_db() as conn:
        _create_tables(conn)
        sets: list[str] = ["updated_at = ?"]
        params: list = [now_str]
        if selected_image_url is not None:
            sets.append("selected_image_url = ?")
            params.append(selected_image_url)
        if selected_coupon_url is not None:
            sets.append("selected_coupon_url = ?")
            params.append(selected_coupon_url)
        if final_tagline is not None:
            sets.append("final_tagline = ?")
            params.append(final_tagline)
        if final_price is not None:
            sets.append("final_price = ?")
            params.append(final_price)
        params.append(push_id)
        cur = conn.execute(
            f"UPDATE push_audits SET {', '.join(sets)} WHERE push_id = ?",
            params,
        )
        return cur.rowcount > 0


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
                   status, review_status, source, material_status, source_trend_id, created_at
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
    source: str = "merchant_upload",
    material_status: str = "ready",
    source_trend_id: str | None = None,
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
            (style_id, enhanced_style_image_url, style_name, tags_json, source, status, review_status, material_status, source_trend_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (style_id, image_url, style_name, tags_json, source, status, review_status, material_status, source_trend_id, now),
        )
        for tag_type, values in style_tags_to_storage_dict(normalized_tags).items():
            for value in values:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO style_tags
                    (style_id, tag_type, tag_value, source, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (style_id, tag_type, value, source, now),
                )
    return {
        "style_id": style_id,
        "style_name": style_name,
        "image_url": image_url,
        "tags": normalized_tags,
        "tryon_enabled": True,
        "status": status,
        "review_status": review_status,
        "source": source,
        "material_status": material_status,
        "source_trend_id": source_trend_id,
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
        if "source" in updates:
            sets.append("source = ?")
            params.append(updates["source"])
        if "material_status" in updates:
            sets.append("material_status = ?")
            params.append(updates["material_status"])
        if "source_trend_id" in updates:
            sets.append("source_trend_id = ?")
            params.append(updates["source_trend_id"])
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


def get_style_by_source_trend_id(source_trend_id: str) -> dict[str, Any] | None:
    init_db(seed=True)
    with connect_db() as conn:
        row = conn.execute(
            """
            SELECT style_id
            FROM styles
            WHERE source_trend_id = ? AND COALESCE(status, 'active') != 'deleted'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (source_trend_id,),
        ).fetchone()
    if not row:
        return None
    return get_style(row["style_id"])


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


def list_selected_template_ids(merchant_id: str) -> list[str]:
    with connect_db() as conn:
        _create_tables(conn)
        rows = conn.execute(
            """
            SELECT template_id
            FROM merchant_template_selections
            WHERE merchant_id = ?
            ORDER BY selected_at
            """,
            (merchant_id,),
        ).fetchall()
    return [row["template_id"] for row in rows]


def save_selected_template_ids(merchant_id: str, template_ids: list[str]) -> list[str]:
    unique_ids = list(dict.fromkeys(template_ids))
    now = _now()
    with connect_db() as conn:
        _create_tables(conn)
        conn.execute("DELETE FROM merchant_template_selections WHERE merchant_id = ?", (merchant_id,))
        for template_id in unique_ids:
            conn.execute(
                """
                INSERT OR REPLACE INTO merchant_template_selections
                (merchant_id, template_id, selected_at)
                VALUES (?, ?, ?)
                """,
                (merchant_id, template_id, now),
            )
    return unique_ids


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


def import_ugc_posts(posts: list[dict[str, Any]]) -> dict[str, int]:
    imported_count = 0
    updated_count = 0
    now = _now()
    with connect_db() as conn:
        _create_tables(conn)
        for post in posts:
            post_id = str(post.get("post_id") or "")
            if not post_id:
                continue
            image_urls = [str(item).strip() for item in (post.get("image_urls") or []) if str(item).strip()]
            page_screenshot_url = str(post.get("page_screenshot_url") or "").strip()
            if image_urls:
                original_first = image_urls[0]
                mirrored_first = mirror_remote_image(original_first, folder="ugc_posts")
                if mirrored_first == original_first and page_screenshot_url:
                    image_urls[0] = page_screenshot_url
                else:
                    image_urls[0] = mirrored_first
            elif page_screenshot_url:
                image_urls = [page_screenshot_url]
            exists = conn.execute("SELECT 1 FROM ugc_posts WHERE post_id = ?", (post_id,)).fetchone()
            conn.execute(
                """
                INSERT INTO ugc_posts (
                    post_id, source, source_url, author_name, title, content,
                    image_urls_json, published_at, like_count, favorite_count, comment_count,
                    raw_tags_json, classification_status, classification_model, classified_at,
                    classification_confidence, is_nail_related, category_guess, is_promotional,
                    promotion_type, promotion_confidence, clean_status, clean_reason, trend_weight,
                    comment_insights_json, comment_sample_count, comment_fetch_status,
                    fetch_status,
                    snapshots_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(post_id) DO UPDATE SET
                    source = excluded.source,
                    source_url = excluded.source_url,
                    author_name = excluded.author_name,
                    title = excluded.title,
                    content = excluded.content,
                    image_urls_json = excluded.image_urls_json,
                    published_at = excluded.published_at,
                    like_count = excluded.like_count,
                    favorite_count = excluded.favorite_count,
                    comment_count = excluded.comment_count,
                    raw_tags_json = excluded.raw_tags_json,
                    classification_status = excluded.classification_status,
                    classification_model = excluded.classification_model,
                    classified_at = excluded.classified_at,
                    classification_confidence = excluded.classification_confidence,
                    is_nail_related = excluded.is_nail_related,
                    category_guess = excluded.category_guess,
                    is_promotional = excluded.is_promotional,
                    promotion_type = excluded.promotion_type,
                    promotion_confidence = excluded.promotion_confidence,
                    clean_status = excluded.clean_status,
                    clean_reason = excluded.clean_reason,
                    trend_weight = excluded.trend_weight,
                    comment_insights_json = excluded.comment_insights_json,
                    comment_sample_count = excluded.comment_sample_count,
                    comment_fetch_status = excluded.comment_fetch_status,
                    fetch_status = excluded.fetch_status,
                    snapshots_json = excluded.snapshots_json,
                    updated_at = excluded.updated_at
                """,
                (
                    post_id,
                    str(post.get("source") or "xiaohongshu"),
                    str(post.get("source_url") or ""),
                    str(post.get("author_name") or ""),
                    str(post.get("title") or ""),
                    str(post.get("content") or ""),
                    json.dumps(image_urls, ensure_ascii=False),
                    str(post.get("published_at") or ""),
                    int(post.get("like_count") or 0),
                    int(post.get("favorite_count") or 0),
                    int(post.get("comment_count") or 0),
                    json.dumps(post.get("raw_tags") or [], ensure_ascii=False),
                    str(post.get("classification_status") or "pending"),
                    str(post.get("classification_model") or ""),
                    str(post.get("classified_at") or ""),
                    float(post.get("classification_confidence") or 0.0),
                    _bool_to_int(post.get("is_nail_related")),
                    str(post.get("category_guess") or "unknown"),
                    _bool_to_int(post.get("is_promotional")),
                    str(post.get("promotion_type") or "unknown"),
                    float(post.get("promotion_confidence") or 0.0),
                    str(post.get("clean_status") or "pending"),
                    str(post.get("clean_reason") or ""),
                    float(post.get("trend_weight") or 1.0),
                    json.dumps(post.get("comment_insights") or {}, ensure_ascii=False),
                    int(post.get("comment_sample_count") or 0),
                    str(post.get("comment_fetch_status") or "pending"),
                    str(post.get("fetch_status") or "ok"),
                    json.dumps(post.get("snapshots") or [], ensure_ascii=False),
                    now,
                    now,
                ),
            )
            if exists:
                updated_count += 1
            else:
                imported_count += 1
    return {"imported_count": imported_count, "updated_count": updated_count, "total_count": imported_count + updated_count}


def list_ugc_posts(limit: int = 500, clean_status_exclude: str | None = "filtered") -> list[dict[str, Any]]:
    with connect_db() as conn:
        _create_tables(conn)
        if clean_status_exclude:
            rows = conn.execute(
                """
                SELECT *
                FROM ugc_posts
                WHERE COALESCE(clean_status, 'pending') != ?
                ORDER BY published_at DESC, like_count DESC
                LIMIT ?
                """,
                (clean_status_exclude, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT *
                FROM ugc_posts
                ORDER BY published_at DESC, like_count DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    return [_ugc_post_payload(dict(row)) for row in rows]


def create_trend_run(triggered_by: str = "manual", total_posts: int = 0, status: str = "pending") -> dict[str, Any]:
    run_id = f"trend-run-{uuid4().hex[:12]}"
    now = _now()
    with connect_db() as conn:
        _create_tables(conn)
        conn.execute(
            """
            INSERT INTO trend_runs
            (run_id, triggered_by, status, total_posts, processed_posts, created_trends,
             error_message, payload_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, 0, 0, '', '{}', ?, ?)
            """,
            (run_id, triggered_by, status, total_posts, now, now),
        )
    return get_trend_run(run_id) or {
        "run_id": run_id,
        "triggered_by": triggered_by,
        "status": status,
        "total_posts": total_posts,
        "processed_posts": 0,
        "created_trends": 0,
        "error_message": "",
        "payload": {},
        "created_at": now,
        "updated_at": now,
    }


def create_trend_pipeline_run(
    *,
    triggered_by: str = "manual",
    input_json_path: str,
    output_json_path: str,
    raw_comments_file: str,
    provider: str = "auto",
    total_posts: int = 0,
    auto_convert_to_draft: bool = False,
    status: str = "pending",
    stage: str = "queued",
) -> dict[str, Any]:
    pipeline_run_id = f"trend-pipeline-{uuid4().hex[:12]}"
    now = _now()
    with connect_db() as conn:
        _create_tables(conn)
        conn.execute(
            """
            INSERT INTO trend_pipeline_runs
            (pipeline_run_id, triggered_by, status, stage, input_json_path, output_json_path,
             raw_comments_file, provider, total_posts, processed_posts, imported_posts,
             updated_posts, generated_trends, converted_drafts, linked_trend_run_id,
             auto_convert_to_draft, error_message, logs_json, payload_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, 0, '', ?, '', '[]', '{}', ?, ?)
            """,
            (
                pipeline_run_id,
                triggered_by,
                status,
                stage,
                input_json_path,
                output_json_path,
                raw_comments_file,
                provider,
                total_posts,
                1 if auto_convert_to_draft else 0,
                now,
                now,
            ),
        )
    return get_trend_pipeline_run(pipeline_run_id) or {
        "pipeline_run_id": pipeline_run_id,
        "triggered_by": triggered_by,
        "status": status,
        "stage": stage,
        "input_json_path": input_json_path,
        "output_json_path": output_json_path,
        "raw_comments_file": raw_comments_file,
        "provider": provider,
        "total_posts": total_posts,
        "processed_posts": 0,
        "imported_posts": 0,
        "updated_posts": 0,
        "generated_trends": 0,
        "converted_drafts": 0,
        "linked_trend_run_id": "",
        "auto_convert_to_draft": auto_convert_to_draft,
        "error_message": "",
        "logs": [],
        "payload": {},
        "created_at": now,
        "updated_at": now,
    }


def update_trend_pipeline_run(
    pipeline_run_id: str,
    *,
    status: str | None = None,
    stage: str | None = None,
    total_posts: int | None = None,
    processed_posts: int | None = None,
    imported_posts: int | None = None,
    updated_posts: int | None = None,
    generated_trends: int | None = None,
    converted_drafts: int | None = None,
    linked_trend_run_id: str | None = None,
    error_message: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    assignments: list[str] = []
    params: list[Any] = []
    if status is not None:
        assignments.append("status = ?")
        params.append(status)
    if stage is not None:
        assignments.append("stage = ?")
        params.append(stage)
    if total_posts is not None:
        assignments.append("total_posts = ?")
        params.append(total_posts)
    if processed_posts is not None:
        assignments.append("processed_posts = ?")
        params.append(processed_posts)
    if imported_posts is not None:
        assignments.append("imported_posts = ?")
        params.append(imported_posts)
    if updated_posts is not None:
        assignments.append("updated_posts = ?")
        params.append(updated_posts)
    if generated_trends is not None:
        assignments.append("generated_trends = ?")
        params.append(generated_trends)
    if converted_drafts is not None:
        assignments.append("converted_drafts = ?")
        params.append(converted_drafts)
    if linked_trend_run_id is not None:
        assignments.append("linked_trend_run_id = ?")
        params.append(linked_trend_run_id)
    if error_message is not None:
        assignments.append("error_message = ?")
        params.append(error_message)
    if payload is not None:
        assignments.append("payload_json = ?")
        params.append(json.dumps(payload, ensure_ascii=False))
    assignments.append("updated_at = ?")
    params.append(_now())
    params.append(pipeline_run_id)
    with connect_db() as conn:
        _create_tables(conn)
        conn.execute(f"UPDATE trend_pipeline_runs SET {', '.join(assignments)} WHERE pipeline_run_id = ?", params)
    return get_trend_pipeline_run(pipeline_run_id)


def append_trend_pipeline_run_log(pipeline_run_id: str, message: str) -> dict[str, Any] | None:
    now = _now()
    with connect_db() as conn:
        _create_tables(conn)
        row = conn.execute(
            "SELECT logs_json FROM trend_pipeline_runs WHERE pipeline_run_id = ?",
            (pipeline_run_id,),
        ).fetchone()
        if not row:
            return None
        logs = _json_loads(row["logs_json"], [])
        if not isinstance(logs, list):
            logs = []
        logs.append({"timestamp": now, "message": message})
        logs = logs[-200:]
        conn.execute(
            "UPDATE trend_pipeline_runs SET logs_json = ?, updated_at = ? WHERE pipeline_run_id = ?",
            (json.dumps(logs, ensure_ascii=False), now, pipeline_run_id),
        )
    return get_trend_pipeline_run(pipeline_run_id)


def get_trend_pipeline_run(pipeline_run_id: str) -> dict[str, Any] | None:
    with connect_db() as conn:
        _create_tables(conn)
        row = conn.execute(
            "SELECT * FROM trend_pipeline_runs WHERE pipeline_run_id = ?",
            (pipeline_run_id,),
        ).fetchone()
    return _trend_pipeline_run_payload(dict(row)) if row else None


def list_trend_pipeline_runs(limit: int = 20) -> list[dict[str, Any]]:
    with connect_db() as conn:
        _create_tables(conn)
        rows = conn.execute(
            """
            SELECT *
            FROM trend_pipeline_runs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [_trend_pipeline_run_payload(dict(row)) for row in rows]


def update_trend_run(
    run_id: str,
    *,
    status: str | None = None,
    total_posts: int | None = None,
    processed_posts: int | None = None,
    created_trends: int | None = None,
    error_message: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    assignments: list[str] = []
    params: list[Any] = []
    if status is not None:
        assignments.append("status = ?")
        params.append(status)
    if total_posts is not None:
        assignments.append("total_posts = ?")
        params.append(total_posts)
    if processed_posts is not None:
        assignments.append("processed_posts = ?")
        params.append(processed_posts)
    if created_trends is not None:
        assignments.append("created_trends = ?")
        params.append(created_trends)
    if error_message is not None:
        assignments.append("error_message = ?")
        params.append(error_message)
    if payload is not None:
        assignments.append("payload_json = ?")
        params.append(json.dumps(payload, ensure_ascii=False))
    assignments.append("updated_at = ?")
    params.append(_now())
    params.append(run_id)
    with connect_db() as conn:
        _create_tables(conn)
        conn.execute(f"UPDATE trend_runs SET {', '.join(assignments)} WHERE run_id = ?", params)
    return get_trend_run(run_id)


def get_trend_run(run_id: str) -> dict[str, Any] | None:
    with connect_db() as conn:
        _create_tables(conn)
        row = conn.execute("SELECT * FROM trend_runs WHERE run_id = ?", (run_id,)).fetchone()
    return _trend_run_payload(dict(row)) if row else None


def _infer_trend_memory_status(status: str, life_cycle: str) -> str:
    if status == "discard":
        return "archived"
    if life_cycle == "衰退期":
        return "declining"
    if status == "promote":
        return "active"
    return "watching"


def _append_score_history(existing_json: Any, *, run_id: str, trend_score: float, confidence: float, life_cycle: str, observed_at: str) -> str:
    history = _json_loads(existing_json, [])
    if not isinstance(history, list):
        history = []
    history.append(
        {
            "run_id": run_id,
            "trend_score": trend_score,
            "confidence": confidence,
            "life_cycle": life_cycle,
            "observed_at": observed_at,
        }
    )
    history = history[-20:]
    return json.dumps(history, ensure_ascii=False)


def replace_trends(trends: list[dict[str, Any]], run_id: str | None = None) -> int:
    """Persist discovered trends with hierarchical matching.

    Matching strategy (most specific first):
    1. Exact trend_id match (canonical SHA256 hash of taxonomy tags)
    2. Core_style name match (current behaviour, catches taxonomy drift)
    3. No match → new trend

    When a match is found via core_style but the canonical trend_id differs
    (e.g. because taxonomy tags evolved), the old ID is recorded in
    ``merged_from_json`` so the lineage is auditable.
    """
    now = _now()
    with connect_db() as conn:
        _create_tables(conn)
        existing_rows = conn.execute("SELECT * FROM trends").fetchall()

        # Build dual indices
        existing_by_trend_id: dict[str, dict[str, Any]] = {}
        existing_by_core_style: dict[str, dict[str, Any]] = {}
        for row in existing_rows:
            d = dict(row)
            tid = str(d.get("trend_id") or "").strip()
            cs = str(d.get("core_style") or "").strip()
            if tid:
                existing_by_trend_id[tid] = d
            if cs:
                existing_by_core_style[cs] = d

        seen_ids: set[str] = set()
        for trend in trends:
            current_trend_id = str(trend.get("trend_id") or "").strip()
            core_style = str(trend.get("core_style") or "").strip()
            if not core_style and not current_trend_id:
                continue

            # ---------- step 1: exact trend_id match ----------
            existing = existing_by_trend_id.get(current_trend_id) if current_trend_id else None

            # ---------- step 2: core_style fallback ----------
            merged_from: list[str] = []
            if not existing and core_style:
                existing = existing_by_core_style.get(core_style)
                if existing:
                    old_id = str(existing.get("trend_id") or "")
                    if old_id and old_id != current_trend_id:
                        # Taxonomy drift detected — record the lineage
                        prev_merged = _json_loads(existing.get("merged_from_json"), [])
                        merged_from = prev_merged if isinstance(prev_merged, list) else []
                        if old_id not in merged_from:
                            merged_from.append(old_id)

            # ---------- determine final trend_id and lifecycle ----------
            if existing:
                trend_id = str(existing["trend_id"])
                identified_at = str(existing.get("identified_at") or now)
                first_seen_at = str(existing.get("first_seen_at") or now)
            else:
                trend_id = current_trend_id
                identified_at = str(trend.get("identified_at") or now)
                first_seen_at = now

            seen_ids.add(trend_id)

            score_history_json = _append_score_history(
                existing.get("score_history_json") if existing else "[]",
                run_id=run_id or "",
                trend_score=float(trend.get("trend_score") or 0.0),
                confidence=float(trend.get("confidence") or 0.0),
                life_cycle=str(trend.get("life_cycle") or "观察期"),
                observed_at=now,
            )
            memory_status = _infer_trend_memory_status(
                str(trend.get("status") or "watch"),
                str(trend.get("life_cycle") or "观察期"),
            )

            conn.execute(
                """
                INSERT OR REPLACE INTO trends (
                    trend_id, core_style, representative_image_url, style_source_image_url,
                    supporting_post_ids_json, supporting_posts_json, keywords_json,
                    trend_score, confidence, life_cycle, reasoning_summary, status,
                    push_status, metrics_json, comment_signal_summary_json,
                    identified_at, expires_at, created_at, updated_at,
                    first_seen_at, last_seen_at, last_run_id, memory_status, score_history_json,
                    data_lifecycle, trend_lifecycle, signal_quality_json, merged_from_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trend_id,
                    core_style,
                    str(trend.get("representative_image_url") or ""),
                    str(trend.get("style_source_image_url") or ""),
                    json.dumps(trend.get("supporting_post_ids") or [], ensure_ascii=False),
                    json.dumps(trend.get("supporting_posts") or [], ensure_ascii=False),
                    json.dumps(trend.get("keywords") or [], ensure_ascii=False),
                    float(trend.get("trend_score") or 0.0),
                    float(trend.get("confidence") or 0.0),
                    str(trend.get("life_cycle") or "观察期"),
                    str(trend.get("reasoning_summary") or ""),
                    str(trend.get("status") or "watch"),
                    str(trend.get("push_status") or "not_pushed"),
                    json.dumps(trend.get("metrics") or {}, ensure_ascii=False),
                    json.dumps(trend.get("comment_signal_summary") or {}, ensure_ascii=False),
                    identified_at,
                    str(trend.get("expires_at") or ""),
                    str(existing["created_at"]) if existing and existing.get("created_at") else now,
                    now,
                    first_seen_at,
                    now,
                    run_id or "",
                    memory_status,
                    score_history_json,
                    str(trend.get("data_lifecycle") or "recent"),
                    str(trend.get("trend_lifecycle") or "insufficient_history"),
                    json.dumps(trend.get("signal_quality_distribution") or trend.get("metrics", {}).get("signal_quality_distribution") or {}, ensure_ascii=False),
                    json.dumps(merged_from, ensure_ascii=False),
                ),
            )

        # ---------- decay: trends not seen this run → watching ----------
        if run_id:
            for eid, existing in existing_by_trend_id.items():
                if eid in seen_ids:
                    continue
                if str(existing.get("memory_status") or "watching") == "archived":
                    continue
                conn.execute(
                    """
                    UPDATE trends
                    SET memory_status = ?, updated_at = ?
                    WHERE trend_id = ?
                    """,
                    ("watching", now, eid),
                )

    return len(trends)


def list_trends(limit: int = 50, status: str | None = None, life_cycle: str | None = None) -> list[dict[str, Any]]:
    with connect_db() as conn:
        _create_tables(conn)
        clauses = ["1 = 1"]
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if life_cycle:
            clauses.append("life_cycle = ?")
            params.append(life_cycle)
        params.append(limit)
        rows = conn.execute(
            f"""
            SELECT *
            FROM trends
            WHERE {' AND '.join(clauses)}
            ORDER BY updated_at DESC, trend_score DESC, identified_at DESC
            """,
            params[:-1] if params else [],
        ).fetchall()
    deduped: list[dict[str, Any]] = []
    seen_core_styles: set[str] = set()
    for row in rows:
        payload = _trend_payload(dict(row))
        core_style = str(payload.get("core_style") or "").strip()
        if core_style:
            if core_style in seen_core_styles:
                continue
            seen_core_styles.add(core_style)
        deduped.append(payload)
        if len(deduped) >= limit:
            break
    deduped.sort(key=lambda item: (float(item.get("trend_score") or 0.0), str(item.get("identified_at") or "")), reverse=True)
    return deduped


def get_trend(trend_id: str) -> dict[str, Any] | None:
    with connect_db() as conn:
        _create_tables(conn)
        row = conn.execute("SELECT * FROM trends WHERE trend_id = ?", (trend_id,)).fetchone()
    return _trend_payload(dict(row)) if row else None


def update_trend_representative_image(trend_id: str, image_url: str) -> dict[str, Any] | None:
    now = _now()
    with connect_db() as conn:
        _create_tables(conn)
        row = conn.execute("SELECT * FROM trends WHERE trend_id = ?", (trend_id,)).fetchone()
        if not row:
            return None
        supporting_posts = _json_loads(row.get("supporting_posts_json"), [])
        if supporting_posts and isinstance(supporting_posts[0], dict):
            supporting_posts[0]["image_url"] = image_url
        conn.execute(
            """
            UPDATE trends
            SET representative_image_url = ?, supporting_posts_json = ?, updated_at = ?
            WHERE trend_id = ?
            """,
            (image_url, json.dumps(supporting_posts, ensure_ascii=False), now, trend_id),
        )
        updated = conn.execute("SELECT * FROM trends WHERE trend_id = ?", (trend_id,)).fetchone()
    return _trend_payload(dict(updated)) if updated else None


def create_merchant_trend_action(
    merchant_id: str,
    trend_id: str,
    action: str,
    note: str = "",
    draft_style_id: str = "",
) -> dict[str, Any]:
    action_id = f"trend-action-{uuid4().hex[:12]}"
    now = _now()
    with connect_db() as conn:
        _create_tables(conn)
        conn.execute(
            """
            INSERT INTO merchant_trend_actions
            (action_id, merchant_id, trend_id, action, note, draft_style_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (action_id, merchant_id, trend_id, action, note, draft_style_id, now),
        )
    return {
        "action_id": action_id,
        "merchant_id": merchant_id,
        "trend_id": trend_id,
        "action": action,
        "note": note,
        "draft_style_id": draft_style_id,
        "created_at": now,
    }


# ===== Data Health (Fix 2: mandatory pipeline stage validation) =====

def get_data_health() -> dict[str, Any]:
    """Return pipeline data health summary for pre-flight checks."""
    with connect_db() as conn:
        _create_tables(conn)
        total_posts = conn.execute("SELECT COUNT(*) AS count FROM ugc_posts").fetchone()["count"]
        classified = conn.execute(
            "SELECT COUNT(*) AS count FROM ugc_posts WHERE classification_status = 'done'"
        ).fetchone()["count"]
        comments_done = conn.execute(
            "SELECT COUNT(*) AS count FROM ugc_posts WHERE comment_fetch_status IN ('done', 'unavailable')"
        ).fetchone()["count"]
        fetch_failed = conn.execute(
            "SELECT COUNT(*) AS count FROM ugc_posts WHERE fetch_status != 'ok'"
        ).fetchone()["count"]
        filtered_out = conn.execute(
            "SELECT COUNT(*) AS count FROM ugc_posts WHERE clean_status = 'filtered'"
        ).fetchone()["count"]
        pending_classification = conn.execute(
            "SELECT COUNT(*) AS count FROM ugc_posts WHERE classification_status = 'pending'"
        ).fetchone()["count"]
        empty_content = conn.execute(
            "SELECT COUNT(*) AS count FROM ugc_posts WHERE (content = '' OR content IS NULL) AND (title = '' OR title IS NULL)"
        ).fetchone()["count"]
        zero_interaction = conn.execute(
            "SELECT COUNT(*) AS count FROM ugc_posts WHERE like_count = 0 AND favorite_count = 0 AND comment_count = 0"
        ).fetchone()["count"]
    return {
        "total_posts": total_posts,
        "classified": classified,
        "comments_done": comments_done,
        "fetch_failed": fetch_failed,
        "filtered_out": filtered_out,
        "pending_classification": pending_classification,
        "empty_content": empty_content,
        "zero_interaction": zero_interaction,
        "ready_for_trend_discovery": classified > 0 and classified >= (total_posts - pending_classification) * 0.8 if total_posts > 0 else False,
        "health": "good" if total_posts > 0 and classified > 0 and classified >= total_posts * 0.5 else "needs_attention",
    }


# ===== Candidate Taxonomy Terms (Fix 5: ops reviewable candidate pool) =====

def upsert_candidate_taxonomy_terms(terms: list[dict[str, Any]], run_id: str = "") -> int:
    """Insert or update candidate taxonomy terms from trend discovery."""
    now = _now()
    upserted = 0
    with connect_db() as conn:
        _create_tables(conn)
        for term in terms:
            candidate_term = str(term.get("candidate_term") or term.get("normalized_form") or "").strip()
            target_field = str(term.get("target_field") or "style_tags").strip()
            if not candidate_term:
                continue
            conn.execute(
                """
                INSERT INTO candidate_taxonomy_terms (
                    candidate_term, normalized_form, target_field, frequency,
                    variant_forms_json, related_official_json, support_post_ids_json,
                    growth_rate_7d, discovered_run_id, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                ON CONFLICT(candidate_term, target_field) DO UPDATE SET
                    frequency = excluded.frequency,
                    variant_forms_json = excluded.variant_forms_json,
                    related_official_json = excluded.related_official_json,
                    support_post_ids_json = excluded.support_post_ids_json,
                    growth_rate_7d = excluded.growth_rate_7d,
                    discovered_run_id = excluded.discovered_run_id,
                    updated_at = excluded.updated_at
                """,
                (
                    candidate_term,
                    str(term.get("normalized_form") or candidate_term),
                    target_field,
                    int(term.get("frequency") or 0),
                    json.dumps(term.get("variant_forms") or [], ensure_ascii=False),
                    json.dumps(term.get("related_official_tags") or [], ensure_ascii=False),
                    json.dumps(term.get("support_post_ids") or [], ensure_ascii=False),
                    float(term.get("growth_rate_7d") or 0.0),
                    run_id,
                    now,
                    now,
                ),
            )
            upserted += 1
    return upserted


def list_candidate_taxonomy_terms(status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    """List candidate taxonomy terms for ops review."""
    with connect_db() as conn:
        _create_tables(conn)
        if status:
            rows = conn.execute(
                """
                SELECT * FROM candidate_taxonomy_terms
                WHERE status = ?
                ORDER BY frequency DESC, updated_at DESC
                LIMIT ?
                """,
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM candidate_taxonomy_terms
                ORDER BY frequency DESC, updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    return [_candidate_taxonomy_term_payload(dict(row)) for row in rows]


def update_candidate_taxonomy_term_status(
    candidate_term: str,
    target_field: str,
    status: str,
    new_candidate_term: str | None = None,
    new_normalized_form: str | None = None,
    new_target_field: str | None = None,
) -> dict[str, Any] | None:
    """Approve or reject a candidate taxonomy term, with optional field edits."""
    now = _now()
    final_term = (new_candidate_term or candidate_term).strip()
    final_normalized = (new_normalized_form or candidate_term).strip()
    final_field = (new_target_field or target_field).strip()
    with connect_db() as conn:
        _create_tables(conn)
        conn.execute(
            """
            UPDATE candidate_taxonomy_terms
            SET status = ?,
                candidate_term = ?,
                normalized_form = ?,
                target_field = ?,
                updated_at = ?
            WHERE candidate_term = ? AND target_field = ?
            """,
            (status, final_term, final_normalized, final_field, now, candidate_term, target_field),
        )
        row = conn.execute(
            "SELECT * FROM candidate_taxonomy_terms WHERE candidate_term = ? AND target_field = ?",
            (final_term, final_field),
        ).fetchone()
    return _candidate_taxonomy_term_payload(dict(row)) if row else None


def _candidate_taxonomy_term_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_term": row["candidate_term"],
        "normalized_form": row["normalized_form"],
        "target_field": row["target_field"],
        "frequency": row["frequency"],
        "variant_forms": _json_loads(row.get("variant_forms_json"), []),
        "related_official_tags": _json_loads(row.get("related_official_json"), []),
        "support_post_ids": _json_loads(row.get("support_post_ids_json"), []),
        "growth_rate_7d": row["growth_rate_7d"],
        "discovered_run_id": row["discovered_run_id"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }

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

        CREATE TABLE IF NOT EXISTS merchant_template_selections (
            merchant_id TEXT NOT NULL,
            template_id TEXT NOT NULL,
            selected_at TEXT NOT NULL,
            PRIMARY KEY(merchant_id, template_id)
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
            material_status TEXT NOT NULL DEFAULT 'ready',
            source_trend_id TEXT,
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
            snapshot_style_name TEXT,
            snapshot_image_url TEXT,
            snapshot_tags_json TEXT NOT NULL DEFAULT '{}',
            snapshot_hot_score REAL,
            snapshot_life_cycle TEXT,
            snapshot_signals_json TEXT NOT NULL DEFAULT '[]',
            snapshot_source_posts_json TEXT NOT NULL DEFAULT '[]',
            snapshot_image_urls_json TEXT NOT NULL DEFAULT '[]',
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

        CREATE TABLE IF NOT EXISTS user_hand_assets (
            user_id TEXT NOT NULL,
            hand_id TEXT NOT NULL,
            image_url TEXT NOT NULL,
            selected INTEGER NOT NULL DEFAULT 0,
            quality_pass INTEGER NOT NULL DEFAULT 1,
            quality_issues_json TEXT NOT NULL DEFAULT '[]',
            nail_art_detected INTEGER NOT NULL DEFAULT 0,
            processing_note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(user_id, hand_id)
        );

        CREATE TABLE IF NOT EXISTS user_hand_profiles (
            hand_profile_id TEXT PRIMARY KEY,
            user_id TEXT,
            hand_id TEXT,
            hand_image_url TEXT NOT NULL,
            skin_tone TEXT NOT NULL DEFAULT '',
            hand_shape TEXT NOT NULL DEFAULT '',
            recommended_colors_json TEXT NOT NULL DEFAULT '[]',
            recommended_styles_json TEXT NOT NULL DEFAULT '[]',
            recommended_nail_shapes_json TEXT NOT NULL DEFAULT '[]',
            analysis_reason TEXT NOT NULL DEFAULT '',
            analysis_mode TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS user_recommendation_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            hand_profile_id TEXT NOT NULL,
            query TEXT NOT NULL DEFAULT '',
            recommendations_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS user_tune_history (
            tune_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            source_style_id TEXT,
            source_style_image_url TEXT NOT NULL,
            tuned_image_url TEXT NOT NULL,
            nail_shape_id TEXT,
            color TEXT,
            user_text TEXT,
            generation_mode TEXT NOT NULL DEFAULT 'mock',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS user_demo_state (
            user_id TEXT PRIMARY KEY,
            current_hand_id TEXT,
            current_hand_profile_id TEXT,
            current_recommendation_snapshot_id TEXT,
            current_tune_id TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS ugc_posts (
            post_id TEXT PRIMARY KEY,
            source TEXT NOT NULL DEFAULT 'xiaohongshu',
            source_url TEXT NOT NULL DEFAULT '',
            author_name TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL DEFAULT '',
            image_urls_json TEXT NOT NULL DEFAULT '[]',
            published_at TEXT NOT NULL DEFAULT '',
            like_count INTEGER NOT NULL DEFAULT 0,
            favorite_count INTEGER NOT NULL DEFAULT 0,
            comment_count INTEGER NOT NULL DEFAULT 0,
            raw_tags_json TEXT NOT NULL DEFAULT '[]',
            classification_status TEXT NOT NULL DEFAULT 'pending',
            classification_model TEXT NOT NULL DEFAULT '',
            classified_at TEXT NOT NULL DEFAULT '',
            classification_confidence REAL NOT NULL DEFAULT 0,
            is_nail_related INTEGER,
            category_guess TEXT NOT NULL DEFAULT 'unknown',
            is_promotional INTEGER,
            promotion_type TEXT NOT NULL DEFAULT 'unknown',
            promotion_confidence REAL NOT NULL DEFAULT 0,
            clean_status TEXT NOT NULL DEFAULT 'pending',
            clean_reason TEXT NOT NULL DEFAULT '',
            trend_weight REAL NOT NULL DEFAULT 1,
            comment_insights_json TEXT NOT NULL DEFAULT '{}',
            comment_sample_count INTEGER NOT NULL DEFAULT 0,
            comment_fetch_status TEXT NOT NULL DEFAULT 'pending',
            fetch_status TEXT NOT NULL DEFAULT 'ok',
            snapshots_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS trend_runs (
            run_id TEXT PRIMARY KEY,
            triggered_by TEXT NOT NULL DEFAULT 'manual',
            status TEXT NOT NULL DEFAULT 'pending',
            total_posts INTEGER NOT NULL DEFAULT 0,
            processed_posts INTEGER NOT NULL DEFAULT 0,
            created_trends INTEGER NOT NULL DEFAULT 0,
            error_message TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS trends (
            trend_id TEXT PRIMARY KEY,
            core_style TEXT NOT NULL DEFAULT '',
            representative_image_url TEXT NOT NULL DEFAULT '',
            style_source_image_url TEXT NOT NULL DEFAULT '',
            supporting_post_ids_json TEXT NOT NULL DEFAULT '[]',
            supporting_posts_json TEXT NOT NULL DEFAULT '[]',
            keywords_json TEXT NOT NULL DEFAULT '[]',
            trend_score REAL NOT NULL DEFAULT 0,
            confidence REAL NOT NULL DEFAULT 0,
            life_cycle TEXT NOT NULL DEFAULT '观察期',
            reasoning_summary TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'watch',
            push_status TEXT NOT NULL DEFAULT 'not_pushed',
            metrics_json TEXT NOT NULL DEFAULT '{}',
            comment_signal_summary_json TEXT NOT NULL DEFAULT '{}',
            identified_at TEXT NOT NULL,
            expires_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            first_seen_at TEXT NOT NULL DEFAULT '',
            last_seen_at TEXT NOT NULL DEFAULT '',
            last_run_id TEXT NOT NULL DEFAULT '',
            memory_status TEXT NOT NULL DEFAULT 'watching',
            score_history_json TEXT NOT NULL DEFAULT '[]',
            data_lifecycle TEXT NOT NULL DEFAULT 'recent',
            trend_lifecycle TEXT NOT NULL DEFAULT 'insufficient_history',
            signal_quality_json TEXT NOT NULL DEFAULT '{}',
            merged_from_json TEXT NOT NULL DEFAULT '[]'
        );

        CREATE TABLE IF NOT EXISTS merchant_trend_actions (
            action_id TEXT PRIMARY KEY,
            merchant_id TEXT NOT NULL,
            trend_id TEXT NOT NULL,
            action TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            draft_style_id TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(trend_id) REFERENCES trends(trend_id)
        );

        CREATE TABLE IF NOT EXISTS trend_pipeline_runs (
            pipeline_run_id TEXT PRIMARY KEY,
            triggered_by TEXT NOT NULL DEFAULT 'manual',
            status TEXT NOT NULL DEFAULT 'pending',
            stage TEXT NOT NULL DEFAULT 'queued',
            input_json_path TEXT NOT NULL DEFAULT '',
            output_json_path TEXT NOT NULL DEFAULT '',
            raw_comments_file TEXT NOT NULL DEFAULT '',
            provider TEXT NOT NULL DEFAULT 'auto',
            total_posts INTEGER NOT NULL DEFAULT 0,
            processed_posts INTEGER NOT NULL DEFAULT 0,
            imported_posts INTEGER NOT NULL DEFAULT 0,
            updated_posts INTEGER NOT NULL DEFAULT 0,
            generated_trends INTEGER NOT NULL DEFAULT 0,
            converted_drafts INTEGER NOT NULL DEFAULT 0,
            linked_trend_run_id TEXT NOT NULL DEFAULT '',
            auto_convert_to_draft INTEGER NOT NULL DEFAULT 0,
            error_message TEXT NOT NULL DEFAULT '',
            logs_json TEXT NOT NULL DEFAULT '[]',
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS candidate_taxonomy_terms (
            candidate_term TEXT NOT NULL,
            normalized_form TEXT NOT NULL,
            target_field TEXT NOT NULL,
            frequency INTEGER NOT NULL DEFAULT 0,
            variant_forms_json TEXT NOT NULL DEFAULT '[]',
            related_official_json TEXT NOT NULL DEFAULT '[]',
            support_post_ids_json TEXT NOT NULL DEFAULT '[]',
            growth_rate_7d REAL NOT NULL DEFAULT 0.0,
            discovered_run_id TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (candidate_term, target_field)
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
    _ensure_column(conn, "styles", "material_status", "TEXT NOT NULL DEFAULT 'ready'")
    _ensure_column(conn, "styles", "source_trend_id", "TEXT")
    _ensure_column(conn, "styles", "deleted_at", "TEXT")
    _ensure_column(conn, "trends", "first_seen_at", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "trends", "last_seen_at", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "trends", "last_run_id", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "trends", "memory_status", "TEXT NOT NULL DEFAULT 'watching'")
    _ensure_column(conn, "trends", "score_history_json", "TEXT NOT NULL DEFAULT '[]'")
    _ensure_column(conn, "ugc_posts", "fetch_status", "TEXT NOT NULL DEFAULT 'ok'")
    _ensure_column(conn, "trends", "data_lifecycle", "TEXT NOT NULL DEFAULT 'recent'")
    _ensure_column(conn, "trends", "trend_lifecycle", "TEXT NOT NULL DEFAULT 'insufficient_history'")
    _ensure_column(conn, "trends", "signal_quality_json", "TEXT NOT NULL DEFAULT '{}'")
    _ensure_column(conn, "trends", "merged_from_json", "TEXT NOT NULL DEFAULT '[]'")
    _ensure_column(conn, "push_audits", "selected_image_url", "TEXT")
    _ensure_column(conn, "push_audits", "selected_coupon_url", "TEXT")
    _ensure_column(conn, "push_audits", "final_tagline", "TEXT")
    _ensure_column(conn, "push_audits", "final_price", "REAL")
    _ensure_column(conn, "push_audits", "snapshot_style_name", "TEXT")
    _ensure_column(conn, "push_audits", "snapshot_image_url", "TEXT")
    _ensure_column(conn, "push_audits", "snapshot_tags_json", "TEXT NOT NULL DEFAULT '{}'")
    _ensure_column(conn, "push_audits", "snapshot_hot_score", "REAL")
    _ensure_column(conn, "push_audits", "snapshot_life_cycle", "TEXT")
    _ensure_column(conn, "push_audits", "snapshot_signals_json", "TEXT NOT NULL DEFAULT '[]'")
    _ensure_column(conn, "push_audits", "snapshot_source_posts_json", "TEXT NOT NULL DEFAULT '[]'")
    _ensure_column(conn, "push_audits", "snapshot_image_urls_json", "TEXT NOT NULL DEFAULT '[]'")
    _ensure_column(conn, "user_hand_assets", "quality_pass", "INTEGER NOT NULL DEFAULT 1")
    _ensure_column(conn, "user_hand_assets", "quality_issues_json", "TEXT NOT NULL DEFAULT '[]'")
    _ensure_column(conn, "user_hand_assets", "nail_art_detected", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "user_hand_assets", "processing_note", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "user_hand_assets", "created_at", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "user_hand_assets", "updated_at", "TEXT NOT NULL DEFAULT ''")


def _ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, definition: str) -> None:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    if any(row["name"] == column_name for row in rows):
        return
    conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def _bool_to_int(value: Any) -> int | None:
    if value is None:
        return None
    return 1 if bool(value) else 0


def _user_hand_asset_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": row["user_id"],
        "hand_id": row["hand_id"],
        "image_url": row["image_url"],
        "selected": bool(row.get("selected")),
        "quality_pass": bool(row.get("quality_pass")),
        "quality_issues": _json_loads(row.get("quality_issues_json"), []),
        "nail_art_detected": bool(row.get("nail_art_detected")),
        "processing_note": row.get("processing_note") or "",
        "created_at": row.get("created_at") or "",
        "updated_at": row.get("updated_at") or "",
    }


def _user_hand_profile_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "hand_profile_id": row["hand_profile_id"],
        "user_id": row.get("user_id"),
        "hand_id": row.get("hand_id"),
        "hand_image_url": row["hand_image_url"],
        "skin_tone": row["skin_tone"],
        "hand_shape": row["hand_shape"],
        "recommended_colors": _json_loads(row.get("recommended_colors_json"), []),
        "recommended_styles": _json_loads(row.get("recommended_styles_json"), []),
        "recommended_nail_shapes": _json_loads(row.get("recommended_nail_shapes_json"), []),
        "analysis_reason": row.get("analysis_reason") or "",
        "analysis_mode": row.get("analysis_mode") or "",
        "created_at": row.get("created_at") or "",
    }


def _recommendation_snapshot_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "snapshot_id": row["snapshot_id"],
        "user_id": row["user_id"],
        "hand_profile_id": row["hand_profile_id"],
        "query": row.get("query") or "",
        "recommendations": _json_loads(row.get("recommendations_json"), []),
        "created_at": row.get("created_at") or "",
    }


def _json_loads(value: Any, default: Any) -> Any:
    try:
        if value is None or value == "":
            return default
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _ugc_post_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "post_id": row["post_id"],
        "source": row["source"],
        "source_url": row["source_url"],
        "author_name": row["author_name"],
        "title": row["title"],
        "content": row["content"],
        "image_urls": _json_loads(row.get("image_urls_json"), []),
        "published_at": row["published_at"],
        "like_count": row["like_count"],
        "favorite_count": row["favorite_count"],
        "comment_count": row["comment_count"],
        "raw_tags": _json_loads(row.get("raw_tags_json"), []),
        "classification_status": row["classification_status"],
        "classification_model": row["classification_model"],
        "classified_at": row["classified_at"],
        "classification_confidence": row["classification_confidence"],
        "is_nail_related": None if row["is_nail_related"] is None else bool(row["is_nail_related"]),
        "category_guess": row["category_guess"],
        "is_promotional": None if row["is_promotional"] is None else bool(row["is_promotional"]),
        "promotion_type": row["promotion_type"],
        "promotion_confidence": row["promotion_confidence"],
        "clean_status": row["clean_status"],
        "clean_reason": row["clean_reason"],
        "trend_weight": row["trend_weight"],
        "comment_insights": _json_loads(row.get("comment_insights_json"), {}),
        "comment_sample_count": row["comment_sample_count"],
        "comment_fetch_status": row["comment_fetch_status"],
        "fetch_status": row.get("fetch_status") or "ok",
        "snapshots": _json_loads(row.get("snapshots_json"), []),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _trend_run_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": row["run_id"],
        "triggered_by": row["triggered_by"],
        "status": row["status"],
        "total_posts": row["total_posts"],
        "processed_posts": row["processed_posts"],
        "created_trends": row["created_trends"],
        "error_message": row["error_message"],
        "payload": _json_loads(row.get("payload_json"), {}),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _trend_pipeline_run_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "pipeline_run_id": row["pipeline_run_id"],
        "triggered_by": row["triggered_by"],
        "status": row["status"],
        "stage": row["stage"],
        "input_json_path": row["input_json_path"],
        "output_json_path": row["output_json_path"],
        "raw_comments_file": row["raw_comments_file"],
        "provider": row["provider"],
        "total_posts": row["total_posts"],
        "processed_posts": row["processed_posts"],
        "imported_posts": row["imported_posts"],
        "updated_posts": row["updated_posts"],
        "generated_trends": row["generated_trends"],
        "converted_drafts": row["converted_drafts"],
        "linked_trend_run_id": row["linked_trend_run_id"],
        "auto_convert_to_draft": bool(row["auto_convert_to_draft"]),
        "error_message": row["error_message"],
        "logs": _json_loads(row.get("logs_json"), []),
        "payload": _json_loads(row.get("payload_json"), {}),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _trend_payload(row: dict[str, Any]) -> dict[str, Any]:
    display_core_style = _normalize_trend_display_name(row["core_style"])
    return {
        "trend_id": row["trend_id"],
        "core_style": display_core_style,
        "representative_image_url": row["representative_image_url"],
        "style_source_image_url": row["style_source_image_url"],
        "supporting_post_ids": _json_loads(row.get("supporting_post_ids_json"), []),
        "supporting_posts": _json_loads(row.get("supporting_posts_json"), []),
        "keywords": _json_loads(row.get("keywords_json"), []),
        "trend_score": row["trend_score"],
        "confidence": row["confidence"],
        "life_cycle": row["life_cycle"],
        "reasoning_summary": row["reasoning_summary"],
        "status": row["status"],
        "push_status": row["push_status"],
        "metrics": _json_loads(row.get("metrics_json"), {}),
        "comment_signal_summary": _json_loads(row.get("comment_signal_summary_json"), {}),
        "identified_at": row["identified_at"],
        "expires_at": row["expires_at"],
        "first_seen_at": row.get("first_seen_at") or row["identified_at"],
        "last_seen_at": row.get("last_seen_at") or row["updated_at"],
        "last_run_id": row.get("last_run_id") or "",
        "memory_status": row.get("memory_status") or "watching",
        "score_history": _json_loads(row.get("score_history_json"), []),
        "data_lifecycle": row.get("data_lifecycle") or "recent",
        "trend_lifecycle": row.get("trend_lifecycle") or "insufficient_history",
        "signal_quality_distribution": _json_loads(row.get("signal_quality_json"), {}),
        "merged_from": _json_loads(row.get("merged_from_json"), []),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _normalize_trend_display_name(core_style: str) -> str:
    text = str(core_style or "").strip()
    if not text:
        return ""
    approved_techniques = set(TAXONOMY_V2_OPTIONS.get("nail_technique", []))
    if text.endswith("美甲") and len(text) > 2:
        trimmed = text[:-2].strip()
        if trimmed in approved_techniques:
            return trimmed
    return text


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


def _merge_tags(seed_tags: dict[str, list[str] | str], tag_rows: list[sqlite3.Row]) -> dict[str, list[str]]:
    merged: dict[str, set[str]] = {key: set(_tag_values(values)) for key, values in seed_tags.items()}
    for row in tag_rows:
        merged.setdefault(row["tag_type"], set()).add(row["tag_value"])
    return {key: sorted(values) for key, values in merged.items()}


def _tag_values(raw: list[str] | str | None) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        value = raw.strip()
        return [value] if value else []
    return [str(value).strip() for value in raw if str(value).strip()]


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


def _push_id_for_trend(trend_id: str) -> str:
    return "trend-" + trend_id.replace("trend_", "")


def _build_push_snapshot(
    conn: sqlite3.Connection,
    style_id: str,
    style_row: dict[str, Any] | sqlite3.Row | None = None,
) -> dict[str, Any]:
    style = dict(style_row) if style_row is not None else {}
    if not style:
        fetched = conn.execute(
            """
            SELECT style_id, style_name, enhanced_style_image_url, tags_json, hot_score, life_cycle
            FROM styles
            WHERE style_id = ?
            """,
            (style_id,),
        ).fetchone()
        style = dict(fetched) if fetched else {}

    tags = json.loads(style.get("tags_json") or "{}") if style else {}
    tag_rows = conn.execute(
        "SELECT tag_type, tag_value FROM style_tags WHERE style_id = ?",
        (style_id,),
    ).fetchall()
    signal_rows = conn.execute(
        "SELECT signal, value, delta, weight FROM style_signals WHERE style_id = ?",
        (style_id,),
    ).fetchall()
    return {
        "style_name": style.get("style_name") or "",
        "image_url": style.get("enhanced_style_image_url") or "",
        "tags": _merge_tags(tags, tag_rows),
        "hot_score": float(style.get("hot_score") or 0),
        "life_cycle": style.get("life_cycle") or "观察期",
        "signals": [dict(signal_row) for signal_row in signal_rows],
    }


def _push_snapshot_from_audit(conn: sqlite3.Connection, audit: dict[str, Any]) -> dict[str, Any]:
    snapshot_tags = json.loads(audit.get("snapshot_tags_json") or "{}")
    snapshot_signals = json.loads(audit.get("snapshot_signals_json") or "[]")
    snapshot_source_posts = json.loads(audit.get("snapshot_source_posts_json") or "[]")
    snapshot_image_urls = json.loads(audit.get("snapshot_image_urls_json") or "[]")
    if audit.get("snapshot_style_name") or audit.get("snapshot_image_url") or snapshot_tags or snapshot_signals:
        return {
            "style_name": audit.get("snapshot_style_name") or "",
            "image_url": audit.get("snapshot_image_url") or "",
            "tags": snapshot_tags if isinstance(snapshot_tags, dict) else {},
            "hot_score": float(audit.get("snapshot_hot_score") or 0),
            "life_cycle": audit.get("snapshot_life_cycle") or "观察期",
            "signals": snapshot_signals if isinstance(snapshot_signals, list) else [],
            "source_posts": snapshot_source_posts if isinstance(snapshot_source_posts, list) else [],
            "style_image_urls": snapshot_image_urls if isinstance(snapshot_image_urls, list) else [],
        }
    return _build_push_snapshot(conn, str(audit.get("style_id") or ""))
