from hashlib import sha1
from urllib.parse import urlparse
import mimetypes

import httpx
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.config import get_settings

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/svg+xml": ".svg",
}


def storage_root() -> Path:
    path = Path(get_settings().storage_dir)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / path
    path.mkdir(parents=True, exist_ok=True)
    return path


async def save_uploaded_image(file: UploadFile, folder: str = "uploads") -> dict:
    content_type = file.content_type or "application/octet-stream"
    suffix = ALLOWED_IMAGE_TYPES.get(content_type)
    if suffix is None:
        raise ValueError(f"unsupported image type: {content_type}")

    data = await file.read()
    if not data:
        raise ValueError("uploaded file is empty")

    target_dir = storage_root() / folder
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}{suffix}"
    path = target_dir / filename
    path.write_bytes(data)

    rel_path = f"{folder}/{filename}"
    return {
        "image_url": public_url(rel_path),
        "filename": filename,
        "content_type": content_type,
        "size_bytes": len(data),
    }


def write_static_text(rel_path: str, content: str) -> str:
    path = storage_root() / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return public_url(rel_path)


def write_static_bytes(rel_path: str, content: bytes) -> str:
    path = storage_root() / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return public_url(rel_path)


def public_url(rel_path: str) -> str:
    return get_settings().public_base_url.rstrip("/") + "/" + rel_path.lstrip("/")


def mirror_remote_image(url: str, folder: str = "ugc_posts") -> str:
    if not url:
        return ""

    stripped = url.strip()
    if not stripped or stripped.startswith("data:"):
        return stripped

    public_base = get_settings().public_base_url.rstrip("/")
    if stripped.startswith(public_base):
        return stripped

    if not stripped.startswith("http"):
        return stripped

    digest = sha1(stripped.encode("utf-8")).hexdigest()
    parsed = urlparse(stripped)
    suffix = Path(parsed.path).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}:
        suffix = ""

    try:
        with httpx.Client(timeout=20, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as client:
            response = client.get(stripped)
            response.raise_for_status()
            content_type = (response.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
            if not suffix:
                suffix = ALLOWED_IMAGE_TYPES.get(content_type) or mimetypes.guess_extension(content_type or "") or ".jpg"
            rel_path = f"{folder}/{digest}{suffix}"
            target = storage_root() / rel_path
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(response.content)
            return public_url(rel_path)
    except Exception:
        return stripped
