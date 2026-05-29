from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.business_db import (
    create_template,
    delete_template,
    list_public_templates,
    list_templates,
)

router = APIRouter()


class CreateTemplateRequest(BaseModel):
    image_url: str
    label: str = ""


class TemplateResponse(BaseModel):
    hand_template_id: str
    hand_image_url: str
    label: str = ""
    source: str = ""
    created_at: str = ""


@router.get("/templates", response_model=list[TemplateResponse])
def get_templates() -> list[TemplateResponse]:
    items = list_templates()
    return [TemplateResponse(
        hand_template_id=t["hand_template_id"],
        hand_image_url=t["hand_image_url"],
        label="",
        source=t.get("source", ""),
        created_at=t.get("created_at", ""),
    ) for t in items]


@router.post("/templates", response_model=TemplateResponse)
def add_template(request: CreateTemplateRequest) -> TemplateResponse:
    if not request.image_url:
        raise HTTPException(status_code=400, detail="image_url is required")
    result = create_template(image_url=request.image_url, label=request.label)
    return TemplateResponse(**result)


@router.delete("/templates/{template_id}")
def remove_template(template_id: str) -> dict:
    ok = delete_template(template_id)
    if not ok:
        raise HTTPException(status_code=404, detail="template not found")
    return {"deleted": True, "template_id": template_id}


@router.get("/templates/public", response_model=list[TemplateResponse])
def get_public_templates() -> list[TemplateResponse]:
    return [TemplateResponse(**t) for t in list_public_templates()]
