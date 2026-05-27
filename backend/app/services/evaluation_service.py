from __future__ import annotations

from app.schemas.evaluation import (
    TARGET_DIMENSIONS,
    DimStat,
    EvalRecord,
    EvalStatsResponse,
    EvalSubmitRequest,
)

_store: list[EvalRecord] = []


def submit_evaluation(req: EvalSubmitRequest) -> EvalRecord:
    dimensions = TARGET_DIMENSIONS.get(req.target_type, [])
    for dim, score in req.scores.items():
        if dim not in dimensions:
            raise ValueError(f"unknown dimension '{dim}' for target_type '{req.target_type}'")
        if score < 1 or score > 5:
            raise ValueError(f"score for '{dim}' must be 1-5, got {score}")

    record = EvalRecord(
        target_type=req.target_type,
        target_id=req.target_id,
        scores=req.scores,
        comment=req.comment,
    )
    _store.append(record)
    return record


def get_stats(target_type: str) -> EvalStatsResponse:
    dimensions = TARGET_DIMENSIONS.get(target_type, [])
    records = [r for r in _store if r.target_type == target_type]

    dim_stats: dict[str, DimStat] = {}
    for dim in dimensions:
        values = [r.scores[dim] for r in records if dim in r.scores]
        dim_stats[dim] = DimStat(
            avg=round(sum(values) / len(values), 2) if values else 0,
            count=len(values),
        )

    return EvalStatsResponse(
        target_type=target_type,
        total_submissions=len(records),
        dimensions=dim_stats,
    )


def list_records(target_type: str | None = None, target_id: str | None = None) -> list[EvalRecord]:
    result = _store
    if target_type:
        result = [r for r in result if r.target_type == target_type]
    if target_id:
        result = [r for r in result if r.target_id == target_id]
    return result
