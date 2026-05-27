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
