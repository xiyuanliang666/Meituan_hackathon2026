from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel
from typing import Any

from app.schemas.style import (
    CompositeRequest,
    CompositeResponse,
    ExtractTagsRequest,
    StyleTagsResponse,
    TryOnRequest,
    TryOnResponse,
    UpdateStyleTagsRequest,
    UploadImageResponse,
)
from app.services.business_db import create_style, delete_style, get_style, update_style
from app.services.image_generation import generate_composite_image, generate_try_on_image
from app.services.image_storage import save_uploaded_image
from app.services.tag_extractor import extract_style_tags, persist_style_tags
from app.services.taxonomy_store import get_style_tags_payload
from app.services.tryon_history import save_tryon_record

router = APIRouter()


# ===== 款式 CRUD =====

class CreateStyleRequest(BaseModel):
    style_name: str
    image_url: str
    tags: dict[str, Any] = {}


class UpdateStyleRequest(BaseModel):
    style_name: str | None = None
    image_url: str | None = None
    tags: dict[str, Any] | None = None
    tryon_enabled: bool | None = None
    life_cycle: str | None = None


class StyleResponse(BaseModel):
    style_id: str
    style_name: str | None = None
    image_url: str = ""
    tags: dict[str, Any] = {}
    tryon_enabled: bool = True
    life_cycle: str = "观察期"
    created_at: str = ""


@router.post("/styles", response_model=StyleResponse)
def add_style(request: CreateStyleRequest) -> StyleResponse:
    if not request.style_name or not request.image_url:
        raise HTTPException(status_code=400, detail="style_name and image_url are required")
    result = create_style(style_name=request.style_name, image_url=request.image_url, tags=request.tags)
    return StyleResponse(
        style_id=result["style_id"],
        style_name=result["style_name"],
        image_url=result["image_url"],
        tags=result["tags"],
        created_at=result["created_at"],
    )


@router.delete("/styles/{style_id}")
def remove_style(style_id: str) -> dict:
    ok = delete_style(style_id)
    if not ok:
        raise HTTPException(status_code=404, detail="style not found")
    return {"deleted": True, "style_id": style_id}


@router.put("/styles/{style_id}", response_model=StyleResponse)
def modify_style(style_id: str, request: UpdateStyleRequest) -> StyleResponse:
    updates = request.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="no fields to update")
    result = update_style(style_id, updates)
    if result is None:
        raise HTTPException(status_code=404, detail="style not found")
    return StyleResponse(
        style_id=result["style_id"],
        style_name=result.get("style_name"),
        image_url=result.get("enhanced_style_image_url", ""),
        tags=result.get("tags", {}),
        life_cycle=result.get("life_cycle", "观察期"),
    )


@router.post("/upload-image", response_model=UploadImageResponse)
async def upload_image(file: UploadFile = File(...)) -> UploadImageResponse:
    try:
        return UploadImageResponse(**await save_uploaded_image(file))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/extract-tags", response_model=StyleTagsResponse)
def extract_tags(request: ExtractTagsRequest) -> StyleTagsResponse:
    if not request.image_url:
        raise HTTPException(status_code=400, detail="image_url is required")
    return extract_style_tags(request.image_url)


@router.get("/styles/{style_id}/tags", response_model=StyleTagsResponse)
def get_style_tags(style_id: str) -> StyleTagsResponse:
    payload = get_style_tags_payload(style_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="style not found")
    return StyleTagsResponse(style_id=style_id, **payload, analysis_mode="stored")


@router.put("/styles/{style_id}/tags", response_model=StyleTagsResponse)
def update_style_tags(style_id: str, request: UpdateStyleTagsRequest) -> StyleTagsResponse:
    if get_style(style_id) is None:
        raise HTTPException(status_code=404, detail="style not found")
    normalized = persist_style_tags(
        style_id=style_id,
        tags=request.model_dump(),
        analysis_mode="manual_review",
    )
    return StyleTagsResponse(style_id=style_id, **normalized, analysis_mode="manual_review")


@router.post("/generate-composite", response_model=CompositeResponse)
def generate_composite(request: CompositeRequest) -> CompositeResponse:
    if not request.style_image_url or not request.template_image_url:
        raise HTTPException(status_code=400, detail="style_image_url and template_image_url are required")
    return generate_composite_image(request)


@router.post("/try-on", response_model=TryOnResponse)
def try_on(request: TryOnRequest) -> TryOnResponse:
    if not request.hand_image_url or not request.style_image_url:
        raise HTTPException(status_code=400, detail="hand_image_url and style_image_url are required")
    response = generate_try_on_image(request)
    if request.user_id and response.result_image_url:
        save_tryon_record(
            user_id=request.user_id,
            hand_image_url=request.hand_image_url,
            style_image_url=request.style_image_url,
            result_image_url=response.result_image_url,
            style_id=request.style_id,
        )
    return response
