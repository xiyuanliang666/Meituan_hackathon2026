import json
from typing import Any

import httpx

from app.config import get_settings


class MultimodalModelError(RuntimeError):
    pass


def is_gemini_enabled() -> bool:
    return get_settings().has_gemini_credentials


def is_qwen_vl_enabled() -> bool:
    return get_settings().has_qwen_credentials


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
    """
    if not api_key:
        raise MultimodalModelError("model API key is not configured")

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
                    {"type": "image_url", "image_url": {"url": image_url}},
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
