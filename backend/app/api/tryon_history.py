from fastapi import APIRouter, HTTPException, Query

from app.schemas.style import TryOnRequest, TryOnResponse
from app.schemas.tryon_history import (
    BatchDeleteRequest,
    RegenerateRequest,
    TryOnHistoryItem,
    TryOnHistoryListResponse,
)
from app.services.image_generation import generate_try_on_image
from app.services.tryon_history import (
    batch_delete_tryon_records,
    delete_tryon_record,
    get_tryon_record,
    list_tryon_history,
    save_tryon_record,
    update_tryon_result,
)

router = APIRouter()


@router.get("/tryon-history", response_model=TryOnHistoryListResponse)
def get_tryon_history(
    user_id: str = Query(..., min_length=1),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> TryOnHistoryListResponse:
    records, total = list_tryon_history(user_id=user_id, limit=limit, offset=offset)
    return TryOnHistoryListResponse(
        records=[TryOnHistoryItem(**r) for r in records],
        total=total,
    )


@router.delete("/tryon-history/{record_id}")
def delete_single_record(record_id: str) -> dict:
    ok = delete_tryon_record(record_id)
    if not ok:
        raise HTTPException(status_code=404, detail="record not found")
    return {"deleted": True, "record_id": record_id}


@router.post("/tryon-history/batch-delete")
def batch_delete_records(request: BatchDeleteRequest) -> dict:
    count = batch_delete_tryon_records(request.record_ids)
    return {"deleted_count": count}


@router.post("/tryon-history/{record_id}/regenerate", response_model=TryOnResponse)
def regenerate_tryon(record_id: str, request: RegenerateRequest | None = None) -> TryOnResponse:
    record = get_tryon_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="record not found")

    hand_url = (request.hand_image_url if request and request.hand_image_url else "") or record["hand_image_url"]
    style_url = (request.style_image_url if request and request.style_image_url else "") or record["style_image_url"]

    tryon_request = TryOnRequest(
        user_id=record["user_id"],
        hand_image_url=hand_url,
        style_image_url=style_url,
        style_id=record.get("style_id"),
    )
    response = generate_try_on_image(tryon_request)
    if response.result_image_url:
        update_tryon_result(record_id, response.result_image_url)
    return response
