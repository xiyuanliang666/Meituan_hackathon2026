from __future__ import annotations

from app.services.business_db import (
    get_data_health,
    list_ugc_posts,
    replace_trends,
    set_pending_push_trends,
    update_trend_run,
    upsert_candidate_taxonomy_terms,
)
from app.services.trend_agent import discover_trends_from_posts
import app.services.taxonomy_store as taxonomy_store


def execute_trend_run(run_id: str, min_support: int, max_trends: int) -> None:
    try:
        # ---------- Fix 2: mandatory pipeline stage validation ----------
        health = get_data_health()
        if health["total_posts"] == 0:
            raise RuntimeError(
                "数据健康检查失败：数据库中没有UGC帖子，请先通过数据源接入导入帖子"
            )
        if health["pending_classification"] > 0 and health["classified"] == 0:
            raise RuntimeError(
                f"数据健康检查失败：{health['pending_classification']} 条帖子尚未分类，"
                "请先运行 classify_ugc_posts.py 完成内容分类后再执行趋势发现"
            )
        if health["empty_content"] > health["total_posts"] * 0.5:
            raise RuntimeError(
                f"数据健康检查失败：{health['empty_content']}/{health['total_posts']} 条帖子正文为空，"
                "请检查抓取链路（fetch_status），必要时使用 Playwright 重新抓取"
            )

        posts = list_ugc_posts(limit=2000, clean_status_exclude="filtered")
        update_trend_run(
            run_id,
            status="running",
            total_posts=len(posts),
            processed_posts=0,
            created_trends=0,
            error_message="",
            payload={"data_health": health, "stage_hint": "posts_loaded"},
        )

        # ---------- Fix 5: pass taxonomy_store to discovery ----------
        payload = discover_trends_from_posts(
            posts,
            min_support=min_support,
            max_trends=max_trends,
            taxonomy_store=taxonomy_store,
            candidate_pool=[],
        )
        update_trend_run(
            run_id,
            processed_posts=int(payload.get("candidate_post_count") or 0),
            created_trends=int(payload.get("trend_count") or 0),
            payload={
                "data_health": health,
                "stage_hint": "trends_discovered",
            },
        )

        # ---------- Fix 5: persist candidate taxonomy terms ----------
        candidate_terms = payload.get("candidate_taxonomy_terms") or []
        if candidate_terms:
            upsert_candidate_taxonomy_terms(candidate_terms, run_id=run_id)
        update_trend_run(
            run_id,
            payload={
                "data_health": health,
                "stage_hint": "candidate_terms_stored",
                "candidate_taxonomy_terms_stored": len(candidate_terms),
            },
        )

        replace_trends(payload["trends"], run_id=run_id)
        update_trend_run(
            run_id,
            payload={
                "data_health": health,
                "stage_hint": "trends_replaced",
                "candidate_taxonomy_terms_stored": len(candidate_terms),
            },
        )

        # 将 promote 趋势写入爆款推送队列（待上架）
        promote_trend_ids = [
            t["trend_id"] for t in payload["trends"]
            if t.get("status") == "promote"
        ]
        update_trend_run(
            run_id,
            payload={
                "data_health": health,
                "stage_hint": "push_queue_preparing",
                "candidate_taxonomy_terms_stored": len(candidate_terms),
                "promote_trend_count": len(promote_trend_ids),
            },
        )
        push_result = (
            set_pending_push_trends(promote_trend_ids, generate_composites=False)
            if promote_trend_ids
            else {"pending": []}
        )

        update_trend_run(
            run_id,
            status="succeeded",
            total_posts=payload["source_post_count"],
            processed_posts=payload["candidate_post_count"],
            created_trends=payload["trend_count"],
            error_message="",
            payload={
                **payload,
                "stage_hint": "completed",
                "candidate_taxonomy_terms_stored": len(candidate_terms),
                "pushed_to_queue": len(promote_trend_ids),
                "push_result": push_result,
            },
        )
    except Exception as exc:
        update_trend_run(
            run_id,
            status="failed",
            error_message=str(exc),
        )
        raise
