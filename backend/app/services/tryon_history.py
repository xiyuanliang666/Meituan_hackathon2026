from __future__ import annotations

from uuid import uuid4

from app.services.business_db import _now, connect_db, init_db


def save_tryon_record(
    user_id: str,
    hand_image_url: str,
    style_image_url: str,
    result_image_url: str,
    style_id: str | None = None,
    hand_id: str | None = None,
) -> dict:
    init_db(seed=True)
    record_id = "tryon-" + uuid4().hex[:12]
    created_at = _now()
    with connect_db() as conn:
        conn.execute(
            """
            INSERT INTO user_tryon_history
            (record_id, user_id, hand_id, style_id,
             hand_image_url, style_image_url, result_image_url, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (record_id, user_id, hand_id, style_id,
             hand_image_url, style_image_url, result_image_url, created_at),
        )
    return {
        "record_id": record_id,
        "user_id": user_id,
        "hand_id": hand_id,
        "style_id": style_id,
        "hand_image_url": hand_image_url,
        "style_image_url": style_image_url,
        "result_image_url": result_image_url,
        "created_at": created_at,
    }


def list_tryon_history(
    user_id: str,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict], int]:
    init_db(seed=True)
    with connect_db() as conn:
        total_row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM user_tryon_history WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        total = int(total_row["cnt"]) if total_row else 0

        rows = conn.execute(
            """
            SELECT record_id, user_id, hand_id, style_id,
                   hand_image_url, style_image_url, result_image_url, created_at
            FROM user_tryon_history
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (user_id, limit, offset),
        ).fetchall()
    return [dict(row) for row in rows], total


def get_tryon_record(record_id: str) -> dict | None:
    init_db(seed=True)
    with connect_db() as conn:
        row = conn.execute(
            """
            SELECT record_id, user_id, hand_id, style_id,
                   hand_image_url, style_image_url, result_image_url, created_at
            FROM user_tryon_history
            WHERE record_id = ?
            """,
            (record_id,),
        ).fetchone()
    return dict(row) if row else None


def delete_tryon_record(record_id: str) -> bool:
    init_db(seed=True)
    with connect_db() as conn:
        cursor = conn.execute(
            "DELETE FROM user_tryon_history WHERE record_id = ?",
            (record_id,),
        )
        return cursor.rowcount > 0


def batch_delete_tryon_records(record_ids: list[str]) -> int:
    init_db(seed=True)
    with connect_db() as conn:
        placeholders = ",".join("?" for _ in record_ids)
        cursor = conn.execute(
            f"DELETE FROM user_tryon_history WHERE record_id IN ({placeholders})",
            record_ids,
        )
        return cursor.rowcount


def update_tryon_result(record_id: str, result_image_url: str) -> bool:
    init_db(seed=True)
    with connect_db() as conn:
        cursor = conn.execute(
            "UPDATE user_tryon_history SET result_image_url = ? WHERE record_id = ?",
            (result_image_url, record_id),
        )
        return cursor.rowcount > 0
