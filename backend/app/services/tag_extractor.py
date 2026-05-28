from hashlib import sha1
from typing import Any

from app.schemas.style import StyleTagsResponse
from app.services.business_db import list_styles, upsert_style_tags
from app.services.dataset_loader import load_evaluation_dataset
from app.services.multimodal_client import (
    MultimodalModelError,
    analyze_image_json_with_gemini,
    analyze_image_json_with_qwen_vl,
    is_gemini_enabled,
    is_qwen_vl_enabled,
)
from app.services.taxonomy_store import (
    build_tagging_prompt,
    style_tags_to_storage_dict,
    validate_style_tags,
)


def extract_style_tags(image_url: str) -> StyleTagsResponse:
    if is_gemini_enabled():
        try:
            return _extract_style_tags_with_model(image_url, provider="gemini")
        except MultimodalModelError:
            pass
    if is_qwen_vl_enabled():
        try:
            return _extract_style_tags_with_model(image_url, provider="qwen")
        except MultimodalModelError:
            pass
    return _extract_style_tags_mock(image_url)


def _extract_style_tags_with_model(image_url: str, provider: str) -> StyleTagsResponse:
    analyze = analyze_image_json_with_gemini if provider == "gemini" else analyze_image_json_with_qwen_vl
    system_prompt, user_prompt = build_tagging_prompt()
    data = analyze(
        image_url=image_url,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )
    style_id = "style-" + sha1(image_url.encode("utf-8")).hexdigest()[:8]
    normalized = validate_style_tags(data)
    return _to_response(
        style_id=style_id,
        tags=normalized,
        analysis_mode="gemini-2.5-flash" if provider == "gemini" else "qwen-vl-plus",
    )


def _extract_style_tags_mock(image_url: str) -> StyleTagsResponse:
    normalized = image_url.lower()
    style_id = "style-" + sha1(image_url.encode("utf-8")).hexdigest()[:8]

    tags: dict[str, Any] = {
        "color_system": ["裸色系", "粉色系"],
        "style_tags": ["甜美", "温柔", "精致"],
        "scene_tags": ["约会", "日常通勤"],
        "season_tags": ["秋", "四季通用"],
        "skin_tone_suitability": ["冷白皮", "自然肤色"],
        "nail_technique": ["渐变", "猫眼"],
        "nail_decoration": ["碎钻/小钻"],
        "nail_finish": "亮面",
        "nail_shape": "杏仁形",
        "nail_length": "中甲",
        "finger_shape": "修长",
        "nail_bed_shape": "标准甲床",
        "candidate_tags": [],
    }

    if "christmas" in normalized or "圣诞" in normalized or "red" in normalized:
        tags = {
            "color_system": ["红色系", "绿色系", "金色系"],
            "style_tags": ["个性", "时尚"],
            "scene_tags": ["派对/夜店"],
            "season_tags": ["圣诞", "冬"],
            "skin_tone_suitability": ["全肤色通用"],
            "nail_technique": ["镜面"],
            "nail_decoration": ["金属箔/金线", "亮片/闪粉"],
            "nail_finish": "镜面光",
            "nail_shape": "方圆形",
            "nail_length": "中甲",
            "finger_shape": "标准",
            "nail_bed_shape": "标准甲床",
            "candidate_tags": [],
        }
    elif "french" in normalized or "法式" in normalized:
        tags = {
            "color_system": ["裸色系"],
            "style_tags": ["法式", "简约", "百搭"],
            "scene_tags": ["日常通勤", "职场"],
            "season_tags": ["四季通用"],
            "skin_tone_suitability": ["全肤色通用"],
            "nail_technique": ["法式", "纯色"],
            "nail_decoration": ["无装饰"],
            "nail_finish": "亮面",
            "nail_shape": "方圆形",
            "nail_length": "短甲",
            "finger_shape": "标准",
            "nail_bed_shape": "标准甲床",
            "candidate_tags": [],
        }
    elif "blue" in normalized or "蓝" in normalized:
        tags = {
            "color_system": ["蓝色系", "银色系"],
            "style_tags": ["酷飒", "清新"],
            "scene_tags": ["约会", "度假"],
            "season_tags": ["夏"],
            "skin_tone_suitability": ["冷白皮"],
            "nail_technique": ["渐变", "镭射/极光"],
            "nail_decoration": ["亮片/闪粉"],
            "nail_finish": "猫眼光",
            "nail_shape": "椭圆形",
            "nail_length": "长甲",
            "finger_shape": "修长",
            "nail_bed_shape": "窄甲床",
            "candidate_tags": [],
        }

    tags = validate_style_tags(tags)
    return _to_response(style_id=style_id, tags=tags, analysis_mode="mock")


def _to_response(style_id: str, tags: dict[str, Any], analysis_mode: str) -> StyleTagsResponse:
    return StyleTagsResponse(
        style_id=style_id,
        color_system=tags.get("color_system", []),
        style_tags=tags.get("style_tags", []),
        scene_tags=tags.get("scene_tags", []),
        season_tags=tags.get("season_tags", []),
        skin_tone_suitability=tags.get("skin_tone_suitability", []),
        nail_technique=tags.get("nail_technique", []),
        nail_decoration=tags.get("nail_decoration", []),
        nail_finish=tags.get("nail_finish", "unknown"),
        nail_shape=tags.get("nail_shape", "unknown"),
        nail_length=tags.get("nail_length", "unknown"),
        finger_shape=tags.get("finger_shape", "unknown"),
        nail_bed_shape=tags.get("nail_bed_shape", "unknown"),
        candidate_tags=tags.get("candidate_tags", []),
        analysis_mode=analysis_mode,
    )


def tags_response_to_dict(tags: StyleTagsResponse) -> dict[str, Any]:
    return tags.model_dump(exclude={"style_id", "analysis_mode"})


def persist_style_tags(
    style_id: str,
    tags: dict[str, Any],
    analysis_mode: str = "manual",
    style_name: str | None = None,
) -> dict[str, Any]:
    normalized = validate_style_tags(tags)
    storage = style_tags_to_storage_dict(normalized)
    upsert_style_tags(
        style_id=style_id,
        tags=storage,
        analysis_mode=analysis_mode,
        style_name=style_name,
        tags_json_full=normalized,
    )
    return normalized


def tag_seed_styles(limit: int = 25) -> dict:
    styles = list_styles(limit=limit)
    modes: dict[str, int] = {}
    updated = 0
    failed = 0

    for style in styles:
        try:
            tags = extract_style_tags(style["enhanced_style_image_url"])
            persist_style_tags(
                style_id=style["style_id"],
                tags=tags_response_to_dict(tags),
                analysis_mode=tags.analysis_mode,
                style_name=_style_name_from_tags(style["style_id"], tags),
            )
            modes[tags.analysis_mode] = modes.get(tags.analysis_mode, 0) + 1
            updated += 1
        except Exception:
            failed += 1

    return {
        "total_styles": len(styles),
        "updated_styles": updated,
        "failed_styles": failed,
        "analysis_modes": modes,
    }


def batch_extract_dataset_tags(limit: int | None = None) -> dict:
    """Batch extract v2 taxonomy tags for all styles in the competition evaluation dataset."""
    dataset = load_evaluation_dataset()
    styles = dataset.styles
    if limit and limit > 0:
        styles = styles[:limit]

    modes: dict[str, int] = {}
    updated = 0
    failed = 0

    for style in styles:
        try:
            tags = extract_style_tags(style.enhanced_style_image_url)
            persist_style_tags(
                style_id=style.style_id,
                tags=tags_response_to_dict(tags),
                analysis_mode=tags.analysis_mode,
                style_name=_style_name_from_tags(style.style_id, tags),
            )
            modes[tags.analysis_mode] = modes.get(tags.analysis_mode, 0) + 1
            updated += 1
        except Exception:
            failed += 1

    return {
        "total_styles": len(styles),
        "updated_styles": updated,
        "failed_styles": failed,
        "analysis_modes": modes,
    }


def _style_name_from_tags(style_id: str, tags: StyleTagsResponse) -> str:
    parts: list[str] = []
    if tags.color_system:
        parts.append(tags.color_system[0])
    if tags.nail_technique:
        parts.append(tags.nail_technique[0])
    if tags.style_tags:
        parts.append(tags.style_tags[0])
    if not parts:
        return f"种子款式 {style_id[-3:]}"
    return "".join(parts[:3])
