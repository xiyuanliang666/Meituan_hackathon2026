from fastapi import APIRouter, HTTPException

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


@router.put("/push-cards/pending", response_model=PendingPushStylesResponse)
def set_pending_push_cards(request: PendingPushStylesRequest) -> PendingPushStylesResponse:
    return update_pending_push_styles(request)


@router.post("/report", response_model=ReportResponse)
def report(request: ReportRequest) -> ReportResponse:
    return generate_report(request)


@router.post("/skills/execute", response_model=SkillExecuteResponse)
def skills_execute(request: SkillExecuteRequest) -> SkillExecuteResponse:
    return execute_skill(request)

