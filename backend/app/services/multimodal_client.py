import base64
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import get_settings


class MultimodalModelError(RuntimeError):
    pass


def is_gemini_enabled() -> bool:
    return get_settings().has_gemini_credentials


def is_qwen_vl_enabled() -> bool:
    return get_settings().has_qwen_credentials


def is_nail_region_vlm_enabled() -> bool:
    return get_settings().has_nail_region_vlm_credentials


def analyze_image_json_with_gemini(image_url: str, system_prompt: str, user_prompt: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.has_gemini_credentials:
        raise MultimodalModelError("GEMINI_API_KEY is not configured")
    return _analyze_image_json_openai_compatible(
        image_url=image_url,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        base_url=settings.gemini_base_url,
        api_key=settings.gemini_api_key,
        model_name=settings.gemini_model_name,
        timeout_seconds=settings.model_timeout_seconds,
    )


def generate_text_json_with_gemini(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.has_gemini_credentials:
        raise MultimodalModelError("GEMINI_API_KEY is not configured")
    return _generate_text_json_openai_compatible(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        base_url=settings.gemini_base_url,
        api_key=settings.gemini_api_key,
        model_name=settings.gemini_model_name,
        timeout_seconds=settings.model_timeout_seconds,
    )


def generate_text_json_with_qwen(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.has_qwen_credentials:
        raise MultimodalModelError("QWEN_API_KEY is not configured")
    return _generate_text_json_openai_compatible(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        base_url=settings.qwen_base_url,
        api_key=settings.qwen_api_key,
        model_name=settings.qwen_vl_model_name,
        timeout_seconds=settings.model_timeout_seconds,
    )


def analyze_image_json_with_qwen_vl(image_url: str, system_prompt: str, user_prompt: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.has_qwen_credentials:
        raise MultimodalModelError("QWEN_API_KEY is not configured")
    return _analyze_image_json_openai_compatible(
        image_url=image_url,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        base_url=settings.qwen_base_url,
        api_key=settings.qwen_api_key,
        model_name=settings.qwen_vl_model_name,
        timeout_seconds=settings.model_timeout_seconds,
    )


def analyze_image_json_with_nail_region_vlm(image_url: str, system_prompt: str, user_prompt: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.has_nail_region_vlm_credentials:
        raise MultimodalModelError("NAIL_REGION_VLM_API_KEY is not configured")
    return _analyze_image_json_openai_compatible(
        image_url=image_url,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        base_url=settings.nail_region_vlm_base_url,
        api_key=settings.nail_region_vlm_api_key,
        model_name=settings.nail_region_vlm_model_name,
        timeout_seconds=settings.model_timeout_seconds,
    )


def _generate_text_json_openai_compatible(
    system_prompt: str,
    user_prompt: str,
    base_url: str,
    api_key: str | None,
    model_name: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    if not api_key:
        raise MultimodalModelError("model API key is not configured")

    endpoint = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_name,
        "temperature": 0.4,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    try:
        return _post_and_parse(endpoint, headers, payload, timeout_seconds)
    except MultimodalModelError:
        payload.pop("response_format", None)
        return _post_and_parse(endpoint, headers, payload, timeout_seconds)


_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "0.0.0.0", "::1"})


def _resolve_image_url(image_url: str, timeout_seconds: float) -> str:
    """Convert local/private image URLs to base64 data URIs.

    Remote model gateways (api.gpt.ge etc.) cannot reach localhost or private IPs.
    We download the image ourselves and embed it as a data URI instead.
    """
    host = (urlparse(image_url).hostname or "").lower()
    local_file_data_uri = _resolve_local_static_file_to_data_uri(image_url)
    if local_file_data_uri:
        return local_file_data_uri

    if host not in _LOCAL_HOSTS and not host.startswith("192.168.") and not host.startswith("10."):
        return image_url

    try:
        with httpx.Client(timeout=min(timeout_seconds, 30.0)) as client:
            resp = client.get(image_url)
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise MultimodalModelError(f"failed to fetch local image: {exc}") from exc

    content_type = resp.headers.get("content-type", "image/png")
    b64 = base64.b64encode(resp.content).decode("ascii")
    return f"data:{content_type};base64,{b64}"


def _resolve_local_static_file_to_data_uri(image_url: str) -> str | None:
    parsed = urlparse(image_url)
    host = (parsed.hostname or "").lower()
    if host and host not in _LOCAL_HOSTS:
        return None
    if not parsed.path.startswith("/static/"):
        return None

    rel_path = parsed.path.removeprefix("/static/").lstrip("/")
    if not rel_path:
        return None

    settings = get_settings()
    candidate = (Path(settings.storage_dir) / rel_path).resolve()
    storage_root = Path(settings.storage_dir).resolve()
    try:
        candidate.relative_to(storage_root)
    except ValueError:
        return None
    if not candidate.exists() or not candidate.is_file():
        return None

    mime = _guess_mime_type(candidate)
    b64 = base64.b64encode(candidate.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _guess_mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".png":
        return "image/png"
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".webp":
        return "image/webp"
    return "image/png"


def _analyze_image_json_openai_compatible(
    image_url: str,
    system_prompt: str,
    user_prompt: str,
    base_url: str,
    api_key: str | None,
    model_name: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    """Call an OpenAI-compatible multimodal chat endpoint and return JSON.

    Gemini and Qwen are configured through their OpenAI-compatible endpoints by
    default. If the provider gateway differs, only this adapter should change.

    Local image URLs are automatically converted to base64 data URIs so that
    remote gateways can access them without direct network reachability.
    """
    if not api_key:
        raise MultimodalModelError("model API key is not configured")

    resolved_url = _resolve_image_url(image_url, timeout_seconds)

    endpoint = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_name,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": resolved_url}},
                ],
            },
        ],
    }

    try:
        return _post_and_parse(endpoint, headers, payload, timeout_seconds)
    except MultimodalModelError:
        payload.pop("response_format", None)
        return _post_and_parse(endpoint, headers, payload, timeout_seconds)


def _post_and_parse(
    endpoint: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
            raw = response.json()
    except httpx.HTTPError as exc:
        raise MultimodalModelError(f"model request failed: {exc}") from exc

    try:
        content = raw["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise MultimodalModelError("model response missing message content") from exc

    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))

    if not isinstance(content, str) or not content.strip():
        raise MultimodalModelError("model response content is empty")

    try:
        return json.loads(_strip_json_fence(content))
    except json.JSONDecodeError as exc:
        raise MultimodalModelError(f"model response is not valid JSON: {content[:200]}") from exc


def _strip_json_fence(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return text
