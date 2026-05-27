from fastapi import APIRouter, File, HTTPException, UploadFile

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
from app.services.business_db import get_style
from app.services.image_generation import generate_composite_image, generate_try_on_image
from app.services.image_storage import save_uploaded_image
from app.services.tag_extractor import extract_style_tags, persist_style_tags
from app.services.taxonomy_store import get_style_tags_payload
from app.services.tryon_history import save_tryon_record

router = APIRouter()


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
