"""
美甲款式微调图像生成服务

整体调整会将原款式图、可选甲型参考图和可选色卡图一起提交给生图模型。

单指微调 (mode=single)：
  - color       → 只替换指定手指颜色
  - french      → 为指定手指添加法式纹样
  - decoration  → 为指定手指添加装饰品

有 OPENAI_API_KEY 且 IMAGE_GENERATION_ENABLED=true 时走真实 API，否则降级 SVG。
"""

import logging
import json
import re
from hashlib import sha1
from pathlib import Path

from app.config import get_settings
from app.services.image_generation import (
    _call_image_edit,
    _write_fallback_svg,
)
from app.services.image_storage import public_url, storage_root, write_static_bytes

logger = logging.getLogger(__name__)

# 从左到右手指名称（设计文档约定只用位置序号，不用解剖学名称）
_FINGER_NAMES = {1: "最左边第一根", 2: "从左往右第二根", 3: "从左往右第三根", 4: "从左往右第四根", 5: "最右边第五根"}


def _shape_dir() -> Path:
    return storage_root() / "tune_references" / "shapes"


def _french_dir() -> Path:
    return storage_root() / "tune_references" / "french"


def _load_reference_manifest(base_dir: Path, *, key: str, default_prompt_builder) -> list[dict[str, str]]:
    manifest_path = base_dir / "manifest.json"
    if not manifest_path.exists():
        return []
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{key} 素材清单 manifest.json 无法读取") from exc

    records = payload.get(key)
    if not isinstance(records, list):
        raise ValueError(f"{key} 素材清单必须包含 {key} 数组")

    valid: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in records:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "").strip()
        label = str(item.get("label") or "").strip()
        image_name = str(item.get("image") or "").strip()
        prompt = str(item.get("prompt") or "").strip()
        if not item_id or not label or not image_name or item_id in seen:
            continue
        image_path = (base_dir / image_name).resolve()
        if image_path.parent != base_dir.resolve() or not image_path.is_file():
            continue
        seen.add(item_id)
        valid.append({
            "id": item_id,
            "label": label,
            "image": image_name,
            "prompt": prompt or default_prompt_builder(label),
        })
    return valid


def _load_shape_manifest() -> list[dict[str, str]]:
    return _load_reference_manifest(
        _shape_dir(),
        key="shapes",
        default_prompt_builder=lambda label: f"将全部指甲调整为参考图中的{label}",
    )


def _load_french_manifest() -> list[dict[str, str]]:
    return _load_reference_manifest(
        _french_dir(),
        key="styles",
        default_prompt_builder=lambda label: f"将法式边缘、走向和留白样式调整为参考图中的{label}",
    )


def get_tune_options() -> dict:
    shapes = _load_shape_manifest()
    french_styles = _load_french_manifest()
    return {
        "shapes": [
            {
                "id": item["id"],
                "label": item["label"],
                "image_url": public_url(f"tune_references/shapes/{item['image']}"),
            }
            for item in shapes
        ],
        "french_styles": [
            {
                "id": item["id"],
                "label": item["label"],
                "image_url": public_url(f"tune_references/french/{item['image']}"),
            }
            for item in french_styles
        ],
    }


def _find_shape(shape_id: str | None) -> dict[str, str] | None:
    if not shape_id:
        return None
    shape = next((item for item in _load_shape_manifest() if item["id"] == shape_id), None)
    if not shape:
        raise ValueError(f"未找到甲型素材：{shape_id}")
    return shape


def _find_french_style(french_style_id: str | None) -> dict[str, str] | None:
    if not french_style_id:
        return None
    style = next((item for item in _load_french_manifest() if item["id"] == french_style_id), None)
    if not style:
        raise ValueError(f"未找到法式素材：{french_style_id}")
    return style


def _normalize_hex_color(color: str) -> str:
    value = color.strip()
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        raise ValueError("颜色必须为 #RRGGBB 格式")
    return value.upper()


def _create_color_card(color: str) -> str:
    from PIL import Image, ImageDraw

    normalized = _normalize_hex_color(color)
    token = normalized[1:].lower()
    rel_path = f"tune_references/color_cards/{token}.png"
    target = storage_root() / rel_path
    if not target.exists():
        image = Image.new("RGB", (1024, 1024), normalized)
        draw = ImageDraw.Draw(image)
        draw.rectangle((24, 24, 1000, 1000), outline="#FFFFFF", width=10)
        from io import BytesIO
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        write_static_bytes(rel_path, buffer.getvalue())
    return public_url(rel_path)


def _build_overall_prompt(
    shape: dict[str, str] | None,
    french_style: dict[str, str] | None,
    color: str | None,
    user_text: str | None,
) -> str:
    image_index = 2
    lines = ["图片1是待编辑的原始美甲款式图。"]
    actions: list[str] = []
    if shape:
        lines.append(f"图片{image_index}是目标甲型参考图，只参考其中的甲型轮廓、长度和比例。")
        actions.append(f"将图片1中的全部指甲调整为图片{image_index}所示甲型")
        image_index += 1
    if french_style:
        lines.append(f"图片{image_index}是目标法式参考图，只参考其中的法式边缘走向、留白比例和法式样式。")
        actions.append(f"将图片1中的全部指甲法式风格调整为图片{image_index}所示样式")
        image_index += 1
    if color:
        lines.append(f"图片{image_index}是目标颜色色卡，请严格匹配色卡中的颜色。")
        actions.append(f"将图片1中的全部指甲颜色替换为图片{image_index}的色卡颜色")
    if actions:
        lines.append("，并".join(actions) + "。")
    elif user_text and user_text.strip():
        lines.append("请仅根据用户的文字描述对图片1中的美甲进行调整。")
    lines.append("保留图片1原有的装饰细节、纹理、光泽、手部姿势、皮肤、背景和构图，除非上面的参考图明确要求修改对应指甲样式。")
    if shape:
        lines.append(f"甲型要求：{shape['prompt']}。")
    if french_style:
        lines.append(f"法式要求：{french_style['prompt']}。仅吸收法式样式本身，不复制参考图中的背景、皮肤、文字或其他无关元素。")
    if user_text and user_text.strip():
        lines.append(f"用户补充要求：{user_text.strip()}。补充要求不得覆盖甲型、法式参考和色卡参考；若没有参考图，则将该描述视为本次美甲微调的主要编辑指令。")
    lines.append("不要复制任何参考图的背景、皮肤、文字、水印或其他无关内容。只修改指甲部分，输出尺寸与图片1一致。")
    return "\n".join(lines)


def _build_single_prompt(
    finger_index: int,
    action: str,
    has_guide_image: bool = False,
    finger_region: list[list[float]] | None = None,
    color: str | None = None,
    french_style: dict[str, str] | None = None,
    decoration: str | None = None,
) -> str:
    finger_desc = _FINGER_NAMES.get(finger_index, f"第{finger_index}根")
    base = f"图中{finger_desc}手指的指甲"

    if action == "color" and color:
        color_desc = _hex_to_desc(color) if color.startswith("#") else color
        prompt = f"将{base}颜色替换为{color_desc}，其余手指保持完全不变，保持原甲型和装饰不变。"
    elif action == "french" and french_style:
        prompt = f"仅将{base}的法式风格调整为参考法式样式，保持该指甲原有甲型、长度和整体构图自然，其余手指完全不变。"
    elif action == "decoration" and decoration:
        prompt = f"在{base}上添加{decoration}装饰，位置自然美观，保持甲型和颜色不变，其余手指完全不变。"
    else:
        prompt = f"对{base}进行微调。"

    if has_guide_image:
        prompt += " 图片2是单指选区标注图，只有高亮虚线框中的那一根指甲允许修改，其余任何指甲都不能变化。"
        if action == "french" and french_style:
            prompt += " 图片3是法式参考图，只参考其中的法式边缘样式、留白比例和走向，不复制其余内容。"
    elif finger_region:
        prompt += f" 该指甲区域的四边形归一化坐标为：{json.dumps(finger_region, ensure_ascii=False)}。请严格将修改限制在这个区域内。"
        if action == "french" and french_style:
            prompt += " 图片2是法式参考图，只参考其中的法式边缘样式、留白比例和走向，不复制其余内容。"
    elif action == "french" and french_style:
        prompt += " 图片2是法式参考图，只参考其中的法式边缘样式、留白比例和走向，不复制其余内容。"
    prompt += "请保持手的姿势、皮肤和背景完全不变，只修改指定手指的指甲。输出图片与原图尺寸一致。"
    return prompt


def _hex_to_desc(hex_color: str) -> str:
    """将十六进制颜色粗略转换为颜色描述，帮助模型理解。"""
    try:
        h = hex_color.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        max_c = max(r, g, b)
        min_c = min(r, g, b)
        saturation = (max_c - min_c) / max_c if max_c > 0 else 0
        lightness = (max_c + min_c) / 2 / 255

        # 极低饱和度（接近无彩色）
        if saturation < 0.08:
            if lightness > 0.85:
                return f"白色（{hex_color}）"
            elif lightness > 0.65:
                return f"浅灰色（{hex_color}）"
            elif lightness > 0.4:
                return f"灰色（{hex_color}）"
            else:
                return f"深灰色（{hex_color}）"

        # 计算色相角
        if max_c == r:
            hue = (g - b) / (max_c - min_c) * 60
        elif max_c == g:
            hue = ((b - r) / (max_c - min_c) + 2) * 60
        else:
            hue = ((r - g) / (max_c - min_c) + 4) * 60
        if hue < 0:
            hue += 360

        # 基本色相判断
        if hue < 20 or hue >= 340:
            base = "粉色" if lightness > 0.65 else "红色"
        elif hue < 45:
            base = "橙色"
        elif hue < 70:
            base = "黄色"
        elif hue < 150:
            base = "绿色"
        elif hue < 195:
            base = "青色"
        elif hue < 255:
            base = "蓝色"
        elif hue < 295:
            base = "紫色"
        else:
            base = "粉紫色" if lightness > 0.55 else "玫红色"

        # 饱和度低 → 莫兰迪/灰调修饰
        if saturation < 0.25:
            modifier = "浅" if lightness > 0.72 else ("深" if lightness < 0.32 else "灰调")
        else:
            modifier = "浅" if lightness > 0.72 else ("深" if lightness < 0.32 else "")
        return f"{modifier}{base}（{hex_color}）"
    except Exception:
        return hex_color


class _MockPromptBundle:
    """用于微调的最简 prompt bundle，只需 task_prompt 字段。"""
    def __init__(self, task_prompt: str):
        self.task_prompt = task_prompt


def tune_nail_image(
    style_image_url: str,
    mode: str,
    nail_shape_id: str | None = None,
    french_style_id: str | None = None,
    color: str | None = None,
    user_text: str | None = None,
    finger_index: int | None = None,
    action: str | None = None,
    french_style: str | None = None,
    decoration: str | None = None,
    guide_image_url: str | None = None,
    finger_region: list[list[float]] | None = None,
) -> dict:
    """
    执行美甲微调，返回 dict(tuned_image_url, generation_mode, warnings)
    """
    settings = get_settings()
    warnings: list[str] = []

    # 构造 prompt
    input_image_urls = [style_image_url]
    if mode == "overall":
        shape = _find_shape(nail_shape_id)
        french_style = _find_french_style(french_style_id)
        normalized_color = _normalize_hex_color(color) if color else None
        if shape:
            input_image_urls.append(public_url(f"tune_references/shapes/{shape['image']}"))
        if french_style:
            input_image_urls.append(public_url(f"tune_references/french/{french_style['image']}"))
        if normalized_color:
            input_image_urls.append(_create_color_card(normalized_color))
        prompt_text = _build_overall_prompt(shape, french_style, normalized_color, user_text)
        op_desc = f"整体微调(shape={nail_shape_id or ''},french={french_style_id or ''},color={normalized_color or ''})"
    else:
        french_style = _find_french_style(french_style_id) if action == "french" else None
        if guide_image_url:
            input_image_urls.append(guide_image_url)
        if french_style:
            input_image_urls.append(public_url(f"tune_references/french/{french_style['image']}"))
        prompt_text = _build_single_prompt(
            finger_index=finger_index or 1,
            action=action or "color",
            has_guide_image=bool(guide_image_url),
            finger_region=finger_region,
            color=color,
            french_style=french_style,
            decoration=decoration,
        )
        op_desc = f"单指微调(finger={finger_index},action={action},french={french_style_id or ''})"

    logger.info("[tune] %s prompt=%s...", op_desc, prompt_text[:80])

    token = sha1(f"{style_image_url}|{prompt_text}".encode()).hexdigest()[:10]

    # 有图片生成凭据时走真实 API
    if settings.has_image_generation_credentials:
        try:
            prompt_bundle = _MockPromptBundle(task_prompt=prompt_text)
            result_url = _call_image_edit(
                token=token,
                prompt_bundle=prompt_bundle,
                input_image_urls=input_image_urls,
                output_folder="generated/tune",
                model_name=settings.image_model_name or "gpt-image-1",
            )
            if result_url:
                logger.info("[tune] 生成成功: %s", result_url)
                return {
                    "tuned_image_url": result_url,
                    "generation_mode": settings.image_model_name or "gpt-image-1",
                    "warnings": warnings,
                }
        except Exception as exc:
            logger.warning("[tune] AI 生图失败，降级 SVG: %s", exc)
            warnings.append(f"AI 生图失败，已降级本地预览：{exc}")

    # 降级：返回原图 SVG 预览
    if not settings.has_image_generation_credentials:
        warnings.append("未开启真实图片生成：请设置 IMAGE_GENERATION_ENABLED=true 并配置 OPENAI_API_KEY。")

    result_url = _write_fallback_svg(
        token=token,
        title=f"微调预览（{op_desc}）",
        left_label="原始款式图",
        left_url=style_image_url,
        right_label="微调目标（需开启AI）",
        right_url=style_image_url,
        output_folder="generated/tune",
    )
    return {
        "tuned_image_url": result_url,
        "generation_mode": "local_svg_fallback",
        "warnings": warnings,
    }
