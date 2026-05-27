import json
import sqlite3
from uuid import uuid4
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from app.config import get_settings
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
        "style_tags",
        "style_signals",
        "ugc_keywords",
        "user_events",
        "push_audits",
        "user_tryon_history",
        "taxonomy_fields",
        "taxonomy_options",
        "taxonomy_submissions",
    ]
    return {table: _count_rows(conn, table) for table in tables}


def list_styles(limit: int = 50) -> list[dict[str, Any]]:
    with connect_db() as conn:
        _create_tables(conn)
        rows = conn.execute(
            """
            SELECT style_id, original_style_image_url, enhanced_style_image_url,
                   style_name, tags_json, hot_score, life_cycle
            FROM styles
            ORDER BY style_id
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    styles = []
    for row in rows:
        item = dict(row)
        item["tags"] = json.loads(item.pop("tags_json") or "{}")
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
                "SELECT status FROM push_audits WHERE push_id = ?",
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
                }
            )
    return candidates


def upsert_push_audit(push_id: str, style_id: str, merchant_id: str, status: str) -> None:
    init_db(seed=True)
    with connect_db() as conn:
        conn.execute(
            """
            INSERT INTO push_audits
            (push_id, style_id, merchant_id, status, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(push_id) DO UPDATE SET
                merchant_id = excluded.merchant_id,
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (push_id, style_id, merchant_id, status, _now()),
        )


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
                   style_name, tags_json, hot_score, life_cycle
            FROM styles
            WHERE style_id = ?
            """,
            (style_id,),
        ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["tags"] = json.loads(item.pop("tags_json") or "{}")
        return item


def _create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS hand_templates (
            hand_template_id TEXT PRIMARY KEY,
            hand_image_url TEXT NOT NULL UNIQUE,
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
            source TEXT NOT NULL DEFAULT 'seed_xlsx',
            created_at TEXT NOT NULL
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
            updated_at TEXT NOT NULL,
            FOREIGN KEY(style_id) REFERENCES styles(style_id)
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


def _seed_from_xlsx(conn: sqlite3.Connection) -> None:
    dataset = load_evaluation_dataset()
    now = _now()

    for index, hand_url in enumerate(dataset.hand_templates, start=1):
        conn.execute(
            """
            INSERT OR IGNORE INTO hand_templates
            (hand_template_id, hand_image_url, source, created_at)
            VALUES (?, ?, 'seed_xlsx', ?)
            """,
            (f"hand-seed-{index:03d}", hand_url, now),
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
