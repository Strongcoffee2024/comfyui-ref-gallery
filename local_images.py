"""Read-only access to images at arbitrary local paths.

This module never copies a file into the gallery library. It only validates a
path, lists folders, and produces cached thumbnails so the browser grid stays
fast. Files stay where they are; deleting them from disk removes them everywhere.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from . import store

GalleryError = store.GalleryError

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
THUMB_LIMIT = (400, 500)
LIST_LIMIT = 5000


def resolve(path: str) -> Path:
    """Validate a user-supplied path and return its absolute location."""
    if not isinstance(path, str) or not path.strip():
        raise GalleryError("path_required")
    try:
        target = Path(path.strip()).expanduser().resolve()
    except OSError as exc:
        raise GalleryError("invalid_path") from exc
    if not target.is_file():
        raise GalleryError("file_not_found", 404)
    if target.suffix.lower() not in IMAGE_SUFFIXES:
        raise GalleryError("unsupported_format")
    if target.stat().st_size > store.MAX_BYTES:
        raise GalleryError("file_too_large", 413)
    return target


def thumb_path(path: str) -> Path:
    """Return a cached WebP thumbnail for an arbitrary local image path."""
    target = resolve(path)
    stat = target.stat()
    key = hashlib.sha256(
        f"{target}|{stat.st_size}|{stat.st_mtime_ns}".encode("utf-8")
    ).hexdigest()[:32]
    cache = store.LIBRARY / "local_thumbs"
    cache.mkdir(parents=True, exist_ok=True)
    out = cache / f"{key}.webp"
    if not out.is_file():
        try:
            with Image.open(target) as source:
                if getattr(source, "n_frames", 1) != 1:
                    raise GalleryError("animated_image")
                image = ImageOps.exif_transpose(source)
                image = Image.alpha_composite(
                    Image.new("RGBA", image.size, "white"), image.convert("RGBA")
                ).convert("RGB")
                image.thumbnail(THUMB_LIMIT, Image.Resampling.LANCZOS)
                image.save(out, "WEBP", quality=86, method=6)
        except GalleryError:
            raise
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise GalleryError("invalid_image") from exc
    return out


def list_folder(folder: str, *, recursive: bool = False) -> dict:
    """List static images in a folder. Non-recursive by default."""
    if not isinstance(folder, str) or not folder.strip():
        raise GalleryError("folder_required")
    try:
        root = Path(folder.strip()).expanduser().resolve()
    except OSError as exc:
        raise GalleryError("invalid_folder") from exc
    if not root.is_dir():
        raise GalleryError("folder_not_found")

    iterator = root.rglob("*") if recursive else root.glob("*")
    files = []
    for path in iterator:
        if len(files) >= LIST_LIMIT:
            break
        try:
            if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            stat = path.stat()
        except OSError:
            continue
        files.append({
            "path": str(path),
            "name": path.name,
            "rel": str(path.relative_to(root)),
            "size": stat.st_size,
        })
    files.sort(key=lambda row: row["rel"].lower())
    return {
        "folder": str(root),
        "files": files,
        "count": len(files),
        "truncated": len(files) >= LIST_LIMIT,
    }
