"""
美甲款式微调图像生成服务

整体调整 (mode=overall)：
  - nail_shape  → 替换全部五根手指甲型
  - color       → 替换全部五根手指颜色
  - 两者可同时指定，合并为一次请求
  - user_text   → 用户自由描述，直接拼入 prompt

单指微调 (mode=single)：
  - color       → 只替换指定手指颜色
  - french      → 为指定手指添加法式纹样
  - decoration  → 为指定手指添加装饰品

有 OPENAI_API_KEY 且 IMAGE_GENERATION_ENABLED=true 时走真实 API，否则降级 SVG。
"""

import logging
from hashlib import sha1

from app.config import get_settings
from app.services.image_generation import (
    _call_image_edit,
    _write_fallback_svg,
)
from app.prompts import build_try_on_prompt_bundle

logger = logging.getLogger(__name__)

# 从左到右手指名称（设计文档约定只用位置序号，不用解剖学名称）
_FINGER_NAMES = {1: "最左边第一根", 2: "从左往右第二根", 3: "从左往右第三根", 4: "从左往右第四根", 5: "最右边第五根"}


def _build_overall_prompt(
    nail_shape: str | None,
    color: str | None,
    user_text: str | None,
) -> str:
    parts: list[str] = []
    if nail_shape:
        parts.append(f"将五根手指的甲型统一调整为{nail_shape}，保持原颜色与装饰不变")
    if color:
        # 如果是十六进制颜色，转换为自然语言描述
        color_desc = _hex_to_desc(color) if color.startswith("#") else color
        parts.append(f"将五根手指的指甲颜色统一替换为{color_desc}，保持原款式的质感与装饰不变")
    if user_text:
        parts.append(user_text)

    base = "。".join(parts) + "。"
    base += "请保持手的姿势、皮肤和背景完全不变，只修改指甲部分。输出图片与原图尺寸一致。"
    return base


def _build_single_prompt(
    finger_index: int,
    action: str,
    color: str | None = None,
    french_style: str | None = None,
    decoration: str | None = None,
) -> str:
    finger_desc = _FINGER_NAMES.get(finger_index, f"第{finger_index}根")
    base = f"图中{finger_desc}手指的指甲"

    if action == "color" and color:
        color_desc = _hex_to_desc(color) if color.startswith("#") else color
        prompt = f"将{base}颜色替换为{color_desc}，其余手指保持完全不变，保持原甲型和装饰不变。"
    elif action == "french" and french_style:
        prompt = f"在{base}上添加{french_style}法式纹样，保持甲型和底色不变，其余手指完全不变。"
    elif action == "decoration" and decoration:
        prompt = f"在{base}上添加{decoration}装饰，位置自然美观，保持甲型和颜色不变，其余手指完全不变。"
    else:
        prompt = f"对{base}进行微调。"

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
    nail_shape: str | None = None,
    color: str | None = None,
    user_text: str | None = None,
    finger_index: int | None = None,
    action: str | None = None,
    french_style: str | None = None,
    decoration: str | None = None,
) -> dict:
    """
    执行美甲微调，返回 dict(tuned_image_url, generation_mode, warnings)
    """
    settings = get_settings()
    warnings: list[str] = []

    # 构造 prompt
    if mode == "overall":
        prompt_text = _build_overall_prompt(nail_shape, color, user_text)
        op_desc = f"整体微调({nail_shape or ''}{color or ''}{user_text or ''})"
    else:
        prompt_text = _build_single_prompt(
            finger_index=finger_index or 1,
            action=action or "color",
            color=color,
            french_style=french_style,
            decoration=decoration,
        )
        op_desc = f"单指微调(finger={finger_index},action={action})"

    logger.info("[tune] %s prompt=%s...", op_desc, prompt_text[:80])

    token = sha1(f"{style_image_url}|{prompt_text}".encode()).hexdigest()[:10]

    # 有图片生成凭据时走真实 API
    if settings.has_image_generation_credentials:
        try:
            prompt_bundle = _MockPromptBundle(task_prompt=prompt_text)
            result_url = _call_image_edit(
                token=token,
                prompt_bundle=prompt_bundle,
                input_image_urls=[style_image_url],
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
