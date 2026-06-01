from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.business_db import (
    create_template,
    delete_template,
    get_template_by_id,
    list_public_templates,
    list_templates,
    update_template,
)
from app.services.hand_analyzer import analyze_seed_hand_templates

router = APIRouter()


class CreateTemplateRequest(BaseModel):
    image_url: str
    label: str = ""
    skin_tone: str = ""
    hand_shape: str = ""


class UpdateTemplateRequest(BaseModel):
    label: str | None = None
    skin_tone: str | None = None
    hand_shape: str | None = None
    analysis_reason: str | None = None


class BatchDeleteTemplatesRequest(BaseModel):
    template_ids: list[str]


class TemplateResponse(BaseModel):
    hand_template_id: str
    hand_image_url: str
    label: str = ""
    skin_tone: str = ""
    hand_shape: str = ""
    source: str = ""
    created_at: str = ""
    recommended_colors: list[str] = []
    recommended_styles: list[str] = []
    recommended_nail_shapes: list[str] = []
    analysis_reason: str = ""
    analysis_mode: str = ""


class AnalyzeTemplatesResponse(BaseModel):
    total_templates: int
    analyzed_templates: int
    failed_templates: int
    analysis_modes: dict[str, int]
    skin_tones: dict[str, int]


@router.get("/templates", response_model=list[TemplateResponse])
def get_templates(source: str | None = Query(default=None)) -> list[TemplateResponse]:
    items = list_templates(source=source)
    return [TemplateResponse(
        hand_template_id=t["hand_template_id"],
        hand_image_url=t["hand_image_url"],
        label=t.get("label", ""),
        skin_tone=t.get("skin_tone", ""),
        hand_shape=t.get("hand_shape", ""),
        source=t.get("source", ""),
        created_at=t.get("created_at", ""),
        recommended_colors=t.get("recommended_colors", []),
        recommended_styles=t.get("recommended_styles", []),
        recommended_nail_shapes=t.get("recommended_nail_shapes", []),
        analysis_reason=t.get("analysis_reason", ""),
        analysis_mode=t.get("analysis_mode", ""),
    ) for t in items]


@router.post("/templates", response_model=TemplateResponse)
def add_template(request: CreateTemplateRequest) -> TemplateResponse:
    if not request.image_url:
        raise HTTPException(status_code=400, detail="image_url is required")
    result = create_template(
        image_url=request.image_url,
        label=request.label,
        skin_tone=request.skin_tone,
        hand_shape=request.hand_shape,
    )
    return TemplateResponse(**result)


@router.get("/templates/public", response_model=list[TemplateResponse])
def get_public_templates() -> list[TemplateResponse]:
    return [TemplateResponse(**t) for t in list_public_templates()]


@router.post("/templates/analyze-seed-hands", response_model=AnalyzeTemplatesResponse)
def analyze_seed_hands(limit: int | None = Query(default=None, ge=1, le=200)) -> AnalyzeTemplatesResponse:
    return AnalyzeTemplatesResponse(**analyze_seed_hand_templates(limit=limit))


@router.post("/templates/batch-delete")
def batch_remove_templates(request: BatchDeleteTemplatesRequest) -> dict:
    deleted = 0
    for template_id in request.template_ids:
        try:
            ok = delete_template(template_id)
        except PermissionError:
            ok = False
        if ok:
            deleted += 1
    return {"requested": len(request.template_ids), "deleted": deleted}


@router.get("/templates/{template_id}", response_model=TemplateResponse)
def get_template(template_id: str) -> TemplateResponse:
    template = get_template_by_id(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="template not found")
    return TemplateResponse(**template)


@router.put("/templates/{template_id}", response_model=TemplateResponse)
def modify_template(template_id: str, request: UpdateTemplateRequest) -> TemplateResponse:
    try:
        result = update_template(template_id, request.model_dump(exclude_none=True))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="template not found")
    return TemplateResponse(**result)


@router.delete("/templates/{template_id}")
def remove_template(template_id: str) -> dict:
    try:
        ok = delete_template(template_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if not ok:
        raise HTTPException(status_code=404, detail="template not found")
    return {"deleted": True, "template_id": template_id}
