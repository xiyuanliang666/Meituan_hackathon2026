from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from pydantic import BaseModel
from typing import Any
from concurrent.futures import ThreadPoolExecutor

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
from app.services.business_db import (
    batch_delete_styles,
    create_style,
    delete_style,
    get_style,
    get_template_by_id,
    list_style_composites,
    save_style_composite,
    update_style,
    update_style_composite_selection,
)
from app.services.image_generation import generate_composite_image, generate_try_on_image
from app.services.image_storage import save_uploaded_image
from app.services.tag_extractor import extract_style_tags, persist_style_tags
from app.services.taxonomy_store import get_style_tags_payload
from app.services.business_db import get_user_hand_asset_by_image
from app.services.tryon_history import save_tryon_record

router = APIRouter()
MAX_COMPOSITE_TEMPLATE_SELECTION = 4


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
    status: str | None = None
    review_status: str | None = None


class StyleResponse(BaseModel):
    style_id: str
    style_name: str | None = None
    image_url: str = ""
    tags: dict[str, Any] = {}
    tryon_enabled: bool = True
    life_cycle: str = "观察期"
    status: str = "active"
    review_status: str = "merchant_confirmed"
    source: str = ""
    material_status: str = "ready"
    source_trend_id: str | None = None
    created_at: str = ""


class BatchDeleteStylesRequest(BaseModel):
    style_ids: list[str]


class UploadDraftRequest(BaseModel):
    image_url: str
    style_name: str | None = None


class BatchUploadDraftItem(BaseModel):
    image_url: str
    style_name: str | None = None


class BatchUploadDraftRequest(BaseModel):
    items: list[BatchUploadDraftItem]


class BatchUploadDraftResponse(BaseModel):
    total: int
    created: int
    items: list[StyleResponse]


class CompositeBatchRequest(BaseModel):
    template_ids: list[str]


class CompositeItemResponse(BaseModel):
    composite_id: str
    style_id: str
    template_id: str
    template_image_url: str
    result_image_url: str
    generation_mode: str = "mock"
    status: str = "generated"
    created_at: str = ""


class CompositeSelectionRequest(BaseModel):
    selected_composite_ids: list[str]


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
        tryon_enabled=result.get("tryon_enabled", True),
        status=result.get("status", "active"),
        review_status=result.get("review_status", "merchant_confirmed"),
        source=result.get("source", ""),
        material_status=result.get("material_status", "ready"),
        source_trend_id=result.get("source_trend_id"),
        created_at=result["created_at"],
    )


@router.post("/styles/upload-draft", response_model=StyleResponse)
def upload_style_draft(request: UploadDraftRequest, background_tasks: BackgroundTasks) -> StyleResponse:
    if not request.image_url:
        raise HTTPException(status_code=400, detail="image_url is required")
    result = _create_style_draft(request.image_url, request.style_name)
    background_tasks.add_task(_extract_tags_for_draft, result["style_id"], request.image_url)
    return StyleResponse(
        style_id=result["style_id"],
        style_name=result["style_name"],
        image_url=result["image_url"],
        tags=result["tags"],
        tryon_enabled=result.get("tryon_enabled", True),
        status=result["status"],
        review_status=result["review_status"],
        source=result.get("source", ""),
        material_status=result.get("material_status", "ready"),
        source_trend_id=result.get("source_trend_id"),
        created_at=result["created_at"],
    )


@router.post("/styles/upload-drafts", response_model=BatchUploadDraftResponse)
def upload_style_drafts(request: BatchUploadDraftRequest, background_tasks: BackgroundTasks) -> BatchUploadDraftResponse:
    if not request.items:
        raise HTTPException(status_code=400, detail="items is required")
    created_items: list[StyleResponse] = []
    for item in request.items:
        if not item.image_url:
            continue
        result = _create_style_draft(item.image_url, item.style_name)
        background_tasks.add_task(_extract_tags_for_draft, result["style_id"], item.image_url)
        created_items.append(
            StyleResponse(
                style_id=result["style_id"],
                style_name=result["style_name"],
                image_url=result["image_url"],
                tags=result["tags"],
                tryon_enabled=result.get("tryon_enabled", True),
                status=result["status"],
                review_status=result["review_status"],
                source=result.get("source", ""),
                material_status=result.get("material_status", "ready"),
                source_trend_id=result.get("source_trend_id"),
                created_at=result["created_at"],
            )
        )
    return BatchUploadDraftResponse(
        total=len(request.items),
        created=len(created_items),
        items=created_items,
    )


def _create_style_draft(image_url: str, style_name: str | None = None) -> dict[str, Any]:
    result = create_style(
        style_name=style_name or "新款式草稿",
        image_url=image_url,
        tags={},
        status="draft",
        review_status="tag_extracting",
    )
    return result


def _extract_tags_for_draft(style_id: str, image_url: str) -> None:
    try:
        tags = extract_style_tags(image_url, style_id=style_id)
        normalized = persist_style_tags(
            style_id=style_id,
            tags=tags.model_dump(exclude={"style_id", "analysis_mode"}),
            analysis_mode=tags.analysis_mode,
        )
        update_style(style_id, {"review_status": "tag_ready", "tags": normalized})
    except Exception:
        update_style(style_id, {"review_status": "tag_failed"})


@router.delete("/styles/{style_id}")
def remove_style(style_id: str) -> dict:
    ok = delete_style(style_id)
    if not ok:
        raise HTTPException(status_code=404, detail="style not found")
    return {"deleted": True, "style_id": style_id}


@router.post("/styles/batch-delete")
def batch_remove_styles(request: BatchDeleteStylesRequest) -> dict:
    if not request.style_ids:
        raise HTTPException(status_code=400, detail="style_ids is required")
    return batch_delete_styles(request.style_ids)


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
        tryon_enabled=bool(result.get("tryon_enabled", True)),
        life_cycle=result.get("life_cycle", "观察期"),
        status=result.get("status", "active"),
        review_status=result.get("review_status", "merchant_confirmed"),
        source=result.get("source", ""),
        material_status=result.get("material_status", "ready"),
        source_trend_id=result.get("source_trend_id"),
        created_at=result.get("created_at", ""),
    )


@router.get("/styles/{style_id}", response_model=StyleResponse)
def read_style(style_id: str) -> StyleResponse:
    result = get_style(style_id)
    if result is None:
        raise HTTPException(status_code=404, detail="style not found")
    return StyleResponse(
        style_id=result["style_id"],
        style_name=result.get("style_name"),
        image_url=result.get("enhanced_style_image_url", ""),
        tags=result.get("tags", {}),
        tryon_enabled=bool(result.get("tryon_enabled", True)),
        life_cycle=result.get("life_cycle", "观察期"),
        status=result.get("status", "active"),
        review_status=result.get("review_status", "merchant_confirmed"),
        source=result.get("source", ""),
        material_status=result.get("material_status", "ready"),
        source_trend_id=result.get("source_trend_id"),
        created_at=result.get("created_at", ""),
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
    return extract_style_tags(request.image_url, style_id=request.style_id)


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
    update_style(style_id, {"review_status": "merchant_confirmed", "tags": normalized})
    return StyleTagsResponse(style_id=style_id, **normalized, analysis_mode="manual_review")


@router.post("/styles/{style_id}/confirm-tags", response_model=StyleResponse)
def confirm_style_tags(style_id: str) -> StyleResponse:
    result = update_style(style_id, {"review_status": "merchant_confirmed"})
    if result is None:
        raise HTTPException(status_code=404, detail="style not found")
    return StyleResponse(
        style_id=result["style_id"],
        style_name=result.get("style_name"),
        image_url=result.get("enhanced_style_image_url", ""),
        tags=result.get("tags", {}),
        tryon_enabled=bool(result.get("tryon_enabled", True)),
        life_cycle=result.get("life_cycle", "观察期"),
        status=result.get("status", "draft"),
        review_status=result.get("review_status", "merchant_confirmed"),
        source=result.get("source", ""),
        material_status=result.get("material_status", "ready"),
        source_trend_id=result.get("source_trend_id"),
        created_at=result.get("created_at", ""),
    )


@router.post("/generate-composite", response_model=CompositeResponse)
def generate_composite(request: CompositeRequest) -> CompositeResponse:
    if not request.style_image_url or not request.template_image_url:
        raise HTTPException(status_code=400, detail="style_image_url and template_image_url are required")
    return generate_composite_image(request)


@router.post("/styles/{style_id}/composites/batch-generate", response_model=list[CompositeItemResponse])
def batch_generate_composites(style_id: str, request: CompositeBatchRequest) -> list[CompositeItemResponse]:
    style = get_style(style_id)
    if style is None:
        raise HTTPException(status_code=404, detail="style not found")
    if not request.template_ids:
        raise HTTPException(status_code=400, detail="template_ids is required")
    if len(request.template_ids) > MAX_COMPOSITE_TEMPLATE_SELECTION:
        raise HTTPException(
            status_code=400,
            detail=f"最多只能选择 {MAX_COMPOSITE_TEMPLATE_SELECTION} 张模板进行合成",
        )

    templates = []
    for template_id in request.template_ids:
        template = get_template_by_id(template_id)
        if not template:
            continue
        templates.append((template_id, template))

    def _generate(item: tuple[str, dict[str, Any]]) -> tuple[str, dict[str, Any], CompositeResponse]:
        template_id, template = item
        generated = generate_composite_image(
            CompositeRequest(
                style_image_url=style["enhanced_style_image_url"],
                template_image_url=template["hand_image_url"],
            )
        )
        return template_id, template, generated

    items: list[CompositeItemResponse] = []
    with ThreadPoolExecutor(max_workers=min(len(templates), 5) or 1) as executor:
        generated_items = list(executor.map(_generate, templates))

    for template_id, template, generated in generated_items:
        saved = save_style_composite(
            style_id=style_id,
            template_id=template_id,
            template_image_url=template["hand_image_url"],
            result_image_url=generated.composite_image_url,
            generation_mode=generated.generation_mode,
        )
        items.append(CompositeItemResponse(**saved))
    update_style(style_id, {"review_status": "composite_ready"})
    return items


@router.get("/styles/{style_id}/composites", response_model=list[CompositeItemResponse])
def get_style_composite_items(style_id: str, status: str | None = None) -> list[CompositeItemResponse]:
    if get_style(style_id) is None:
        raise HTTPException(status_code=404, detail="style not found")
    return [CompositeItemResponse(**item) for item in list_style_composites(style_id, status=status)]


@router.put("/styles/{style_id}/composites/selection")
def select_style_composites(style_id: str, request: CompositeSelectionRequest) -> dict:
    if get_style(style_id) is None:
        raise HTTPException(status_code=404, detail="style not found")
    return update_style_composite_selection(style_id, request.selected_composite_ids)


@router.post("/styles/{style_id}/publish", response_model=StyleResponse)
def publish_style(style_id: str) -> StyleResponse:
    result = update_style(style_id, {"status": "active", "review_status": "published"})
    if result is None:
        raise HTTPException(status_code=404, detail="style not found")
    return StyleResponse(
        style_id=result["style_id"],
        style_name=result.get("style_name"),
        image_url=result.get("enhanced_style_image_url", ""),
        tags=result.get("tags", {}),
        tryon_enabled=bool(result.get("tryon_enabled", True)),
        life_cycle=result.get("life_cycle", "观察期"),
        status=result.get("status", "active"),
        review_status=result.get("review_status", "published"),
        source=result.get("source", ""),
        material_status=result.get("material_status", "ready"),
        source_trend_id=result.get("source_trend_id"),
        created_at=result.get("created_at", ""),
    )


@router.post("/try-on", response_model=TryOnResponse)
def try_on(request: TryOnRequest) -> TryOnResponse:
    if not request.hand_image_url or not request.style_image_url:
        raise HTTPException(status_code=400, detail="hand_image_url and style_image_url are required")
    response = generate_try_on_image(request)
    if request.user_id and response.result_image_url:
        hand_asset = get_user_hand_asset_by_image(request.user_id, request.hand_image_url)
        save_tryon_record(
            user_id=request.user_id,
            hand_image_url=request.hand_image_url,
            style_image_url=request.style_image_url,
            result_image_url=response.result_image_url,
            style_id=request.style_id,
            hand_id=hand_asset.get("hand_id") if hand_asset else None,
        )
    return response
