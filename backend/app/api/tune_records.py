from fastapi import APIRouter, HTTPException

from app.services.business_db import get_demo_tune_record_group, list_demo_tune_record_groups

router = APIRouter()


@router.get("/tune-records")
def tune_record_groups() -> dict:
    return {"groups": list_demo_tune_record_groups()}


@router.get("/tune-records/{root_tryon_record_id}")
def tune_record_group_detail(root_tryon_record_id: str) -> dict:
    group = get_demo_tune_record_group(root_tryon_record_id)
    if not group:
        raise HTTPException(status_code=404, detail="tune record group not found")
    return group
