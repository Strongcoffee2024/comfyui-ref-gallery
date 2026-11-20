"""Persistent user reference-image library for ComfyUI.

No artwork is bundled with this node. Every image comes from a user upload or a
user-pointed folder. All files live under ComfyUI's user directory and are never
downloaded from the network.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES = 20 * 1024 * 1024
MAX_PIXELS = 32_000_000
PREVIEW_LIMIT = (1200, 1500)
THUMB_LIMIT = (400, 500)
ID_RE = re.compile(r"^g-[0-9a-f]{32}$")

try:
    import folder_paths
    _USER_DIR = Path(folder_paths.get_user_directory())
except Exception:  # pragma: no cover - standalone import
    _USER_DIR = Path.home() / ".comfyui" / "user"

LIBRARY = Path(
    os.environ.get("COMFYUI_REF_GALLERY_DIR", str(_USER_DIR / "ref_gallery"))
).resolve()
INDEX_PATH = "data/index.json"
DIRS = {"full": "full", "preview": "preview", "thumb": "thumbs"}
EXT = {"full": ".png", "preview": ".webp", "thumb": ".webp"}

_LOCK = threading.RLock()


class GalleryError(ValueError):
    def __init__(self, code: str, status: int = 400):
        self.code = code
        self.status = status
        super().__init__(code)


def _safe(root: Path, relative: str) -> Path:
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise GalleryError("storage_error", 500)
    return target


def _text(value, *, required=False, limit=120) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise GalleryError("invalid_metadata")
    value = value.strip()
    if any(ord(ch) < 32 for ch in value) or len(value) > limit:
        raise GalleryError("invalid_metadata")
    if required and not value:
        raise GalleryError("name_required")
    return value


def _index_file() -> Path:
    path = _safe(LIBRARY, INDEX_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def read_records() -> list[dict]:
    with _LOCK:
        path = _index_file()
        if not path.is_file():
            return []
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise GalleryError("storage_error", 500) from exc
        if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
            raise GalleryError("storage_error", 500)
        return rows


def get_record(identity: str) -> dict:
    if not isinstance(identity, str) or not ID_RE.fullmatch(identity):
        raise GalleryError("invalid_id")
    for row in read_records():
        if row.get("id") == identity:
            return row
    raise GalleryError("unknown_id", 404)


def metadata() -> dict:
    rows = read_records()
    return {"total": len(rows), "library": str(LIBRARY)}


def asset_path(kind: str, filename: str) -> Path:
    if kind not in DIRS or Path(filename).name != filename or "\\" in filename:
        raise GalleryError("invalid_asset")
    identity = Path(filename).stem
    row = get_record(identity)
    expected = f"{DIRS[kind]}/{identity}{EXT[kind]}"
    if row.get(kind) != expected:
        raise GalleryError("invalid_asset")
    target = _safe(LIBRARY, expected)
    if not target.is_file():
        raise GalleryError("missing_asset", 404)
    return target


def _decode(data: bytes, filename: str) -> Image.Image:
    if len(data) > MAX_BYTES:
        raise GalleryError("file_too_large", 413)
    if not isinstance(filename, str) or not filename or len(filename) > 255:
        raise GalleryError("invalid_filename")
    if Path(filename).name != filename or "/" in filename or "\\" in filename:
        raise GalleryError("invalid_filename")
    try:
        with Image.open(BytesIO(data)) as source:
            if source.format not in {"PNG", "JPEG", "WEBP"}:
                raise GalleryError("unsupported_format")
            if getattr(source, "n_frames", 1) != 1:
                raise GalleryError("animated_image")
            if source.width * source.height > MAX_PIXELS:
                raise GalleryError("too_many_pixels")
            source.load()
            image = ImageOps.exif_transpose(source)
            has_alpha = "A" in image.getbands() or "transparency" in image.info
            return image.convert("RGBA" if has_alpha else "RGB")
    except GalleryError:
        raise
    except Image.DecompressionBombError as exc:
        raise GalleryError("too_many_pixels") from exc
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
        raise GalleryError("invalid_image") from exc


def _make_derivatives(image: Image.Image, identity: str, work: Path) -> tuple[dict, tuple[int, int]]:
    # Flatten alpha onto white so the IMAGE tensor is always RGB, while the
    # stored PNG keeps its transparency.
    opaque = Image.alpha_composite(
        Image.new("RGBA", image.size, "white"), image.convert("RGBA")
    ).convert("RGB")
    image.save(work / "full.png", format="PNG")

    sizes = {}
    for kind, limit, quality in (
        ("preview", PREVIEW_LIMIT, 90),
        ("thumb", THUMB_LIMIT, 86),
    ):
        copy = opaque.copy()
        copy.thumbnail(limit, Image.Resampling.LANCZOS)
        copy.save(work / f"{kind}.webp", format="WEBP", quality=quality, method=6)
        sizes[kind] = copy.size

    full_bytes = (work / "full.png").read_bytes()
    return {
        "full": f"{DIRS['full']}/{identity}.png",
        "preview": f"{DIRS['preview']}/{identity}.webp",
        "thumb": f"{DIRS['thumb']}/{identity}.webp",
        "w": image.width,
        "h": image.height,
        "thumb_w": sizes["thumb"][0],
        "thumb_h": sizes["thumb"][1],
        "bytes": len(full_bytes),
        "sha256": hashlib.sha256(full_bytes).hexdigest(),
    }, sizes["thumb"]


def _new_row(image, identity, work, filename, name, other_name, category, angle, tags) -> dict:
    """Build one index row and its derivative files inside ``work``.

    Does not touch the index or the final asset paths; the caller commits both.
    """
    meta, thumb_size = _make_derivatives(image, identity, work)
    return {
        "id": identity,
        "name": name,
        "other_name": other_name or name,
        "category": category,
        "angle": angle,
        "tags": [t.strip() for t in re.split(r"[,，\s]+", tags) if t.strip()],
        "w": meta["w"],
        "h": meta["h"],
        "thumb_w": thumb_size[0],
        "thumb_h": thumb_size[1],
        "bytes": meta["bytes"],
        "sha256": meta["sha256"],
        "original_filename": filename,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "full": meta["full"],
        "preview": meta["preview"],
        "thumb": meta["thumb"],
    }


def _commit_index(rows: list[dict]) -> None:
    """Atomically replace the whole index with ``rows`` (one write, one fsync)."""
    index = _index_file()
    temp_index = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=index.parent,
            prefix=".index-", suffix=".tmp", delete=False,
        ) as fh:
            temp_index = Path(fh.name)
            json.dump(rows, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp_index, index)
    except OSError as exc:
        raise GalleryError("storage_error", 500) from exc
    finally:
        if temp_index and temp_index.exists():
            temp_index.unlink(missing_ok=True)


def _destinations(identity: str) -> dict[str, Path]:
    return {k: _safe(LIBRARY, f"{DIRS[k]}/{identity}{EXT[k]}") for k in DIRS}


def _move_derivatives(work: Path, destinations: dict[str, Path]) -> list[Path]:
    """Move staged files into place, rolling back this image on any failure."""
    moved: list[Path] = []
    try:
        for kind, target in destinations.items():
            src = work / ("full.png" if kind == "full" else f"{kind}.webp")
            os.replace(src, target)
            moved.append(target)
    except OSError:
        for target in moved:
            target.unlink(missing_ok=True)
        raise GalleryError("storage_error", 500)
    return moved


def import_image(
    data: bytes,
    *,
    filename: str,
    name: str,
    other_name: str = "",
    category: str = "",
    angle: str = "unknown",
    tags: str = "",
) -> dict:
    """Validate one image, build derivatives, and atomically commit it."""
    image = _decode(data, filename)
    name = _text(name, required=True)
    other_name = _text(other_name)
    category = _text(category) or "未分类"
    tags = _text(tags, limit=240)
    if angle not in ("unknown", "front", "top", "bottom", "side", "diagonal"):
        raise GalleryError("invalid_metadata")

    identity = "g-" + uuid.uuid4().hex
    with _LOCK:
        LIBRARY.mkdir(parents=True, exist_ok=True)
        destinations = _destinations(identity)
        for target in destinations.values():
            target.parent.mkdir(parents=True, exist_ok=True)
        if any(p.exists() for p in destinations.values()):
            raise GalleryError("storage_error", 500)

        moved: list[Path] = []
        committed = False
        try:
            with tempfile.TemporaryDirectory(prefix=".import-", dir=LIBRARY) as tmp:
                work = Path(tmp)
                row = _new_row(
                    image, identity, work, filename, name, other_name,
                    category, angle, tags,
                )
                moved = _move_derivatives(work, destinations)
                existing = read_records()
                if any(r.get("id") == identity for r in existing):
                    raise GalleryError("storage_error", 500)
                _commit_index(existing + [row])
                committed = True
            return row
        except GalleryError:
            raise
        except (OSError, ValueError) as exc:
            raise GalleryError("storage_error", 500) from exc
        finally:
            if not committed:
                for target in moved:
                    target.unlink(missing_ok=True)


def delete_record(identity: str) -> dict:
    row = get_record(identity)
    with _LOCK:
        remaining = [r for r in read_records() if r.get("id") != identity]
        _commit_index(remaining)
        for kind in DIRS:
            _safe(LIBRARY, row[kind]).unlink(missing_ok=True)
        return {"deleted": identity}


def import_folder(folder: str, *, category: str = "", limit: int = 2000) -> dict:
    """Import every static image in a user-specified folder (non-recursive).

    Derivatives are staged one image at a time, but the index is written only
    once at the end. Rewriting and fsync-ing the full index on every single
    image made large folders progressively slower (O(n^2)).
    """
    source = Path(folder).expanduser()
    if not source.is_dir():
        raise GalleryError("folder_not_found")
    files = sorted(
        p for p in source.iterdir()
        if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    )[:limit]

    ok, failed = 0, []
    new_rows: list[dict] = []
    stored: list[Path] = []

    with _LOCK:
        LIBRARY.mkdir(parents=True, exist_ok=True)
        existing = read_records()
        try:
            for path in files:
                try:
                    image = _decode(path.read_bytes(), path.name)
                    name = _text(path.stem, required=True)
                    cat = _text(category) or "未分类"
                    identity = "g-" + uuid.uuid4().hex
                    destinations = _destinations(identity)
                    if any(p.exists() for p in destinations.values()):
                        raise GalleryError("storage_error", 500)
                    with tempfile.TemporaryDirectory(prefix=".import-", dir=LIBRARY) as tmp:
                        row = _new_row(
                            image, identity, Path(tmp), path.name, name, name,
                            cat, "unknown", "",
                        )
                        stored.extend(_move_derivatives(Path(tmp), destinations))
                    new_rows.append(row)
                    ok += 1
                except GalleryError as exc:
                    failed.append({"file": path.name, "error": exc.code})
                except (OSError, ValueError):
                    failed.append({"file": path.name, "error": "storage_error"})
            if new_rows:
                _commit_index(existing + new_rows)
        except Exception:
            for target in stored:
                target.unlink(missing_ok=True)
            raise
    return {"imported": ok, "failed": failed, "total": len(files)}
