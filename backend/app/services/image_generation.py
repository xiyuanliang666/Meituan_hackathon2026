import base64
import io
import logging
import struct
from hashlib import sha1
from html import escape
from urllib.parse import unquote_to_bytes

import httpx

from app.config import get_settings
from app.prompts import (
    NailTryOnPromptBundle,
    build_try_on_prompt_bundle,
    format_prompt_for_image_edit_api,
)
from app.schemas.style import CompositeRequest, CompositeResponse, TryOnRequest, TryOnResponse
from app.services.image_storage import write_static_bytes, write_static_text

logger = logging.getLogger(__name__)


def choose_generation_size(width: int, height: int) -> str:
    """Pick API output size from original image dimensions (before any resize)."""
    if width <= 0 or height <= 0:
        return "1024x1024"

    aspect = height / width

    if aspect > 1.15:
        return "1024x1536"

    if (width / height) > 1.15:
        return "1536x1024"

    return "1024x1024"


def generate_composite_image(request: CompositeRequest) -> CompositeResponse:
    settings = get_settings()
    token = sha1(f"{request.style_image_url}|{request.template_image_url}".encode("utf-8")).hexdigest()[:10]
    prompt_bundle = build_try_on_prompt_bundle()

    if settings.has_image_generation_credentials:
        result = _try_generate_with_image_models(
            token=token,
            prompt_bundle=prompt_bundle,
            input_image_urls=[request.template_image_url, request.style_image_url],
            output_folder="generated/composite",
        )
        if result:
            url, model_name = result
            return CompositeResponse(composite_image_url=url, generation_mode=model_name)

    result_url = _write_fallback_svg(
        token=token,
        title="AI 合成图预览",
        left_label="裸手模板",
        left_url=request.template_image_url,
        right_label="款式参考",
        right_url=request.style_image_url,
        output_folder="generated/composite",
    )
    return CompositeResponse(
        composite_image_url=result_url,
        generation_mode="local_svg_fallback",
    )


def generate_try_on_image(request: TryOnRequest) -> TryOnResponse:
    settings = get_settings()
    token = sha1(f"{request.hand_image_url}|{request.style_image_url}".encode("utf-8")).hexdigest()[:10]
    warnings: list[str] = []

    prompt_bundle = build_try_on_prompt_bundle()

    if settings.has_image_generation_credentials:
        result = _try_generate_with_image_models(
            token=token,
            prompt_bundle=prompt_bundle,
            input_image_urls=[request.hand_image_url, request.style_image_url],
            output_folder="generated/try-on",
        )
        if result:
            url, model_name = result
            return TryOnResponse(result_image_url=url, generation_mode=model_name, warnings=warnings)

        warnings.append("图片生成模型调用失败，已回退本地预览。")

    result_url = _write_fallback_svg(
        token=token,
        title="AI 试戴预览",
        left_label="用户手图",
        left_url=request.hand_image_url,
        right_label="款式参考",
        right_url=request.style_image_url,
        output_folder="generated/try-on",
    )
    if not settings.has_image_generation_credentials:
        warnings.append(
            "未开启真实图片生成：请设置 IMAGE_GENERATION_ENABLED=true 并配置 OPENAI_API_KEY。"
        )
    return TryOnResponse(
        result_image_url=result_url,
        generation_mode="local_svg_fallback",
        warnings=warnings,
    )


def _image_model_candidates() -> list[str]:
    settings = get_settings()
    return [settings.image_model_name or "gpt-image-1"]


def _try_generate_with_image_models(
    token: str,
    prompt_bundle: NailTryOnPromptBundle,
    input_image_urls: list[str],
    output_folder: str,
) -> tuple[str, str] | None:
    last_error: str | None = None
    for model_name in _image_model_candidates():
        try:
            result_url = _call_image_edit(
                token=token,
                prompt_bundle=prompt_bundle,
                input_image_urls=input_image_urls,
                output_folder=output_folder,
                model_name=model_name,
            )
            if result_url:
                logger.info("image generation succeeded with model=%s", model_name)
                return result_url, model_name
        except Exception as exc:
            last_error = str(exc)
            logger.warning("image generation failed for model=%s: %s", model_name, exc)
    if last_error:
        logger.warning("all image edit models failed, last_error=%s", last_error)
    return None


def _call_image_edit(
    token: str,
    prompt_bundle: NailTryOnPromptBundle,
    input_image_urls: list[str],
    output_folder: str,
    model_name: str,
) -> str | None:
    """Edit the first hand image using later images as visual style references."""
    settings = get_settings()
    if not 1 <= len(input_image_urls) <= 16:
        raise ValueError("image edit requires 1 to 16 input images")

    input_bytes = [_download_image(url) for url in input_image_urls]
    canvas_bytes = input_bytes[0]
    input_width, input_height = read_image_dimensions(canvas_bytes)
    size = choose_generation_size(input_width, input_height)
    logger.info(
        "Selected generation size: %s, input=%sx%s, references=%s",
        size,
        input_width,
        input_height,
        max(len(input_bytes) - 1, 0),
    )

    prompt_parts = format_prompt_for_image_edit_api(task_prompt=prompt_bundle.task_prompt)
    logger.info("Prompt task=%d chars", len(prompt_parts["task_prompt"]))

    endpoint = settings.openai_base_url.rstrip("/") + "/images/edits"
    files = [
        ("image[]", (f"input-{index + 1}{_file_extension(image_bytes)}", image_bytes, _content_type(image_bytes)))
        for index, image_bytes in enumerate(input_bytes)
    ]
    data = {
        "model": model_name,
        "prompt": prompt_parts["api_prompt"],
        "size": size,
        "input_fidelity": "high",
    }
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
    timeout = max(settings.model_timeout_seconds, 180)

    sizes_to_try = [size]
    if size != "1024x1024":
        sizes_to_try.append("1024x1024")

    fidelity_modes_to_try = [True, False]  # gpt-image-2 不支持 input_fidelity

    last_detail = ""
    last_code = 0
    for attempt_size in sizes_to_try:
        for use_fidelity in fidelity_modes_to_try:
            req_data = dict(data)
            req_data["size"] = attempt_size
            if not use_fidelity:
                req_data.pop("input_fidelity", None)
            with httpx.Client(timeout=timeout) as client:
                response = client.post(endpoint, headers=headers, data=req_data, files=files)
            if response.status_code < 400:
                last_code = 0
                break
            last_code = response.status_code
            last_detail = response.text[:500]
            if "input_fidelity" in last_detail.lower() and use_fidelity:
                logger.info("Model %s does not support input_fidelity, retrying without it", model_name)
                continue
            if "unsupported size" in last_detail.lower() and attempt_size != sizes_to_try[-1]:
                logger.info("Size %s not supported by %s, retrying with %s", attempt_size, model_name, sizes_to_try[-1])
                break
            raise RuntimeError(f"HTTP {last_code}: {last_detail}")
        if last_code == 0:
            break
    if last_code >= 400:
        raise RuntimeError(f"HTTP {last_code}: {last_detail}")

    payload = response.json()
    image_payload = payload.get("data", [{}])[0]
    output_bytes: bytes | None = None
    if image_payload.get("b64_json"):
        output_bytes = base64.b64decode(image_payload["b64_json"])
    elif image_payload.get("url"):
        with httpx.Client(timeout=60, follow_redirects=True) as client:
            remote = client.get(str(image_payload["url"]))
            remote.raise_for_status()
            output_bytes = remote.content

    if not output_bytes:
        return None

    output_bytes = trim_uniform_white_margins(output_bytes)
    return write_static_bytes(f"{output_folder}/{token}.png", output_bytes)


def read_image_dimensions(content: bytes) -> tuple[int, int]:
    """Read width/height from original bytes — no resize or crop."""
    if content.startswith(b"\xff\xd8"):
        return _jpeg_dimensions(content)
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return _png_dimensions(content)
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return _webp_dimensions(content)
    raise ValueError("unsupported image format for dimension probe")


def trim_uniform_white_margins(
    output_bytes: bytes,
    threshold: int = 248,
    max_trim_ratio: float = 0.12,
) -> bytes:
    """
    Remove solid white letterbox bars at top/bottom only.
    Does not crop into hand content; skips if trim would remove > max_trim_ratio of height.
    """
    try:
        from PIL import Image
    except ImportError:
        return output_bytes

    image = Image.open(io.BytesIO(output_bytes)).convert("RGB")
    width, height = image.size
    if height < 32:
        return output_bytes

    pixels = image.load()

    def row_is_margin(y: int) -> bool:
        white = 0
        for x in range(width):
            r, g, b = pixels[x, y]
            if r >= threshold and g >= threshold and b >= threshold:
                white += 1
        return white / width >= 0.97

    top = 0
    while top < height and row_is_margin(top):
        top += 1
    bottom = height - 1
    while bottom > top and row_is_margin(bottom):
        bottom -= 1

    trim_total = top + (height - 1 - bottom)
    if trim_total <= 0 or trim_total / height > max_trim_ratio:
        return output_bytes

    cropped = image.crop((0, top, width, bottom + 1))
    logger.info("Trimmed uniform white margins: top=%s bottom=%s new_size=%sx%s", top, height - bottom - 1, width, cropped.height)
    buffer = io.BytesIO()
    cropped.save(buffer, format="PNG")
    return buffer.getvalue()


def _png_dimensions(content: bytes) -> tuple[int, int]:
    if content[12:16] == b"IHDR":
        width, height = struct.unpack(">II", content[16:24])
        return int(width), int(height)
    raise ValueError("invalid PNG IHDR")


def _jpeg_dimensions(content: bytes) -> tuple[int, int]:
    index = 2
    while index < len(content):
        if content[index] != 0xFF:
            index += 1
            continue
        marker = content[index + 1]
        index += 2
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            height, width = struct.unpack(">HH", content[index + 3 : index + 7])
            return int(width), int(height)
        if index + 1 >= len(content):
            break
        segment_length = struct.unpack(">H", content[index : index + 2])[0]
        index += segment_length
    raise ValueError("JPEG SOF not found")


def _webp_dimensions(content: bytes) -> tuple[int, int]:
    if content[12:16] == b"VP8 ":
        width, height = struct.unpack("<HH", content[26:30])
        return width & 0x3FFF, height & 0x3FFF
    if content[12:16] == b"VP8L":
        bits = struct.unpack("<I", content[21:25])[0]
        width = (bits & 0x3FFF) + 1
        height = ((bits >> 14) & 0x3FFF) + 1
        return width, height
    if content[12:16] == b"VP8X":
        width = 1 + struct.unpack("<I", content[24:27] + b"\x00")[0]
        height = 1 + struct.unpack("<I", content[27:30] + b"\x00")[0]
        return width, height
    raise ValueError("unsupported WEBP layout")


def _download_image(url: str) -> bytes:
    if url.startswith("data:"):
        header, _, payload = url.partition(",")
        if not payload:
            raise ValueError("invalid data URI image")
        if ";base64" in header:
            return base64.b64decode(payload)
        return unquote_to_bytes(payload)
    if url.startswith("http://127.0.0.1") or url.startswith("http://localhost"):
        path_part = url.split("/static/", 1)[-1]
        from app.services.image_storage import storage_root

        return (storage_root() / path_part).read_bytes()

    with httpx.Client(timeout=60, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.content


def _write_fallback_svg(
    token: str,
    title: str,
    left_label: str,
    left_url: str,
    right_label: str,
    right_url: str,
    output_folder: str,
) -> str:
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="760" viewBox="0 0 1200 760">
  <rect width="1200" height="760" fill="#fff7f6"/>
  <text x="60" y="72" font-size="34" font-family="Arial, sans-serif" font-weight="700" fill="#28202a">{escape(title)}</text>
  <text x="60" y="112" font-size="18" font-family="Arial, sans-serif" fill="#7a6674">本地兜底预览：真实生成模型未启用或调用失败时返回，保证 Demo 可展示。</text>
  <rect x="60" y="150" width="510" height="510" rx="18" fill="#ffffff" stroke="#e6c9d6" stroke-width="2"/>
  <rect x="630" y="150" width="510" height="510" rx="18" fill="#ffffff" stroke="#e6c9d6" stroke-width="2"/>
  <image href="{escape(left_url)}" x="90" y="180" width="450" height="420" preserveAspectRatio="xMidYMid meet"/>
  <image href="{escape(right_url)}" x="660" y="180" width="450" height="420" preserveAspectRatio="xMidYMid meet"/>
  <text x="315" y="625" font-size="24" text-anchor="middle" font-family="Arial, sans-serif" fill="#4a3b46">{escape(left_label)}</text>
  <text x="885" y="625" font-size="24" text-anchor="middle" font-family="Arial, sans-serif" fill="#4a3b46">{escape(right_label)}</text>
  <path d="M570 405 C595 380, 605 380, 630 405" fill="none" stroke="#d45a8c" stroke-width="8" stroke-linecap="round"/>
  <path d="M614 382 L640 405 L614 428" fill="none" stroke="#d45a8c" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/>
</svg>"""
    return write_static_text(f"{output_folder}/{token}.svg", svg)


def _content_type(content: bytes) -> str:
    if content.lstrip().startswith(b"<svg"):
        return "image/svg+xml"
    if content.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if content.startswith(b"RIFF") and b"WEBP" in content[:16]:
        return "image/webp"
    return "image/png"


def _file_extension(content: bytes) -> str:
    if content.lstrip().startswith(b"<svg"):
        return ".svg"
    if content.startswith(b"\xff\xd8"):
        return ".jpg"
    if content.startswith(b"RIFF") and b"WEBP" in content[:16]:
        return ".webp"
    return ".png"
