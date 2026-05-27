from fastapi import APIRouter, HTTPException, Query

from app.schemas.evaluation import EvalRecord, EvalStatsResponse, EvalSubmitRequest
from app.services.evaluation_service import get_stats, list_records, submit_evaluation

router = APIRouter()


@router.post("/evaluations", response_model=EvalRecord)
def create_evaluation(request: EvalSubmitRequest) -> EvalRecord:
    try:
        return submit_evaluation(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/evaluations/stats", response_model=EvalStatsResponse)
def evaluation_stats(target_type: str = Query(..., description="try_on | chat | hand_analysis")) -> EvalStatsResponse:
    from app.schemas.evaluation import TARGET_DIMENSIONS

    if target_type not in TARGET_DIMENSIONS:
        raise HTTPException(status_code=400, detail=f"unknown target_type '{target_type}'")
    return get_stats(target_type)


@router.get("/evaluations", response_model=list[EvalRecord])
def evaluation_records(
    target_type: str | None = Query(default=None),
    target_id: str | None = Query(default=None),
) -> list[EvalRecord]:
    return list_records(target_type=target_type, target_id=target_id)
