from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.schemas.operations import (
    AuditPushCardRequest,
    AuditPushCardResponse,
    PendingPushStylesRequest,
    PendingPushStylesResponse,
    PushCardResponse,
    ReportRequest,
    ReportResponse,
    SkillExecuteRequest,
    SkillExecuteResponse,
)
from app.services.business_db import update_push_composites
from app.services.operations import (
    audit_push_card,
    execute_skill,
    generate_report,
    list_push_cards,
    update_pending_push_styles,
)

router = APIRouter()


@router.get("/push-cards", response_model=list[PushCardResponse])
def push_cards() -> list[PushCardResponse]:
    return list_push_cards()


@router.post("/push-cards/{push_id}/audit", response_model=AuditPushCardResponse)
def audit(push_id: str, request: AuditPushCardRequest) -> AuditPushCardResponse:
    if request.action not in {"accepted", "rejected"}:
        raise HTTPException(status_code=400, detail="action must be accepted or rejected")
    return audit_push_card(push_id, request)


class UpdatePushCompositesRequest(BaseModel):
    image_urls: list[str]


@router.put("/push-cards/{push_id}/composites")
def update_composites(push_id: str, request: UpdatePushCompositesRequest):
    ok = update_push_composites(push_id, request.image_urls)
    if not ok:
        raise HTTPException(status_code=404, detail="push card not found")
    return {"push_id": push_id, "updated": True}


@router.put("/push-cards/pending", response_model=PendingPushStylesResponse)
def set_pending_push_cards(request: PendingPushStylesRequest) -> PendingPushStylesResponse:
    return update_pending_push_styles(request)


@router.post("/report", response_model=ReportResponse)
def report(request: ReportRequest) -> ReportResponse:
    return generate_report(request)


@router.post("/skills/execute", response_model=SkillExecuteResponse)
def skills_execute(request: SkillExecuteRequest) -> SkillExecuteResponse:
    return execute_skill(request)

