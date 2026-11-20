"""comfyui-ref-gallery: browse a personal reference library and output an IMAGE.

Zero bundled artwork. Images are added only through user upload or a user-pointed
local folder. Code is MIT; any images a user imports keep their own rights.
"""
from __future__ import annotations

import asyncio
import logging
import random
from pathlib import Path

import numpy as np
import torch
from aiohttp import web
from PIL import Image, ImageOps
from server import PromptServer

from . import store

MAX_BYTES = store.MAX_BYTES


def _tensor_from(path) -> tuple[torch.Tensor, int, int]:
    with Image.open(path) as source:
        img = ImageOps.exif_transpose(source).convert("RGBA")
        img = Image.alpha_composite(Image.new("RGBA", img.size, "white"), img).convert("RGB")
        width, height = img.size
        tensor = torch.from_numpy(np.asarray(img).astype(np.float32) / 255.0).unsqueeze(0)
    return tensor, width, height


class RefGallery:
    """Pick one image from the personal library by ID."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image_id": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "点击「浏览参考图库」选图；也可直接填入图片 ID。",
                }),
            },
        }

    RETURN_TYPES = ("IMAGE", "INT", "INT", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("image", "width", "height", "image_id", "name", "description")
    FUNCTION = "load_image"
    CATEGORY = "image/Ref Gallery"
    DESCRIPTION = "个人参考图库：上传/导入自己的图片，浏览选图并输出 IMAGE。"

    @classmethod
    def VALIDATE_INPUTS(cls, image_id=""):
        try:
            store.asset_path("full", store.get_record(image_id)["full"].split("/")[-1])
        except store.GalleryError as exc:
            return str(exc.code)
        return True

    @classmethod
    def IS_CHANGED(cls, image_id=""):
        try:
            record = store.get_record(image_id)
            path = store.asset_path("full", record["full"].split("/")[-1])
            return f"{record['sha256']}:{path.stat().st_mtime_ns}"
        except (store.GalleryError, OSError):
            return image_id

    def load_image(self, image_id=""):
        record = store.get_record(image_id)
        path = store.asset_path("full", record["full"].split("/")[-1])
        tensor, width, height = _tensor_from(path)
        description = " / ".join(
            str(part) for part in (record.get("category"), record.get("angle"), record.get("tags"))
            if part and (not isinstance(part, list) or part)
        )
        if isinstance(record.get("tags"), list):
            description = " / ".join(
                p for p in [record.get("category"), record.get("angle"), *record["tags"]] if p
            )
        return (tensor, width, height, image_id, record["name"], description)


class RandomRefGallery(RefGallery):
    """Draw a random image each run; optional dice preview and lock."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "category": ("STRING", {"default": "all", "multiline": False,
                    "tooltip": "分类筛选；all 表示全部。Category filter; all = every image."}),
            },
            "optional": {
                "image_id": ("STRING", {"default": "", "multiline": False,
                    "tooltip": "骰子当前选中的 ID；锁定后固定使用它。"}),
                "locked": ("BOOLEAN", {"default": False, "tooltip": "锁定当前图片，运行时不再随机。"}),
            },
        }

    FUNCTION = "load_random"
    DESCRIPTION = "点击骰子随机预览，无需运行；锁定后固定，解锁后每次运行重新抽取。"

    @classmethod
    def _candidates(cls, category="all"):
        rows = []
        for row in store.read_records():
            if category not in ("all", "") and row.get("category") != category:
                continue
            try:
                store.asset_path("full", row["full"].split("/")[-1])
            except store.GalleryError:
                continue
            rows.append(row)
        if not rows:
            raise store.GalleryError("no_images", 400)
        return rows

    @classmethod
    def VALIDATE_INPUTS(cls, category="all", image_id="", locked=False):
        try:
            if locked:
                return super().VALIDATE_INPUTS(image_id)
            cls._candidates(category)
        except store.GalleryError as exc:
            return str(exc.code)
        return True

    @classmethod
    def IS_CHANGED(cls, category="all", image_id="", locked=False):
        if locked:
            return super().IS_CHANGED(image_id)
        return str(random.getrandbits(64))

    def load_random(self, category="all", image_id="", locked=False):
        if locked:
            selected = store.get_record(image_id)
        else:
            selected = random.choice(self._candidates(category))
        result = super().load_image(selected["id"])
        return {
            "ui": {"picked_id": [selected["id"]], "picked_name": [selected["name"]]},
            "result": result,
        }


routes = PromptServer.instance.routes


def _json_error(exc: store.GalleryError):
    return web.json_response({"error": exc.code}, status=exc.status,
                             headers={"Cache-Control": "no-store"})


@routes.get("/ref_gallery/catalog")
async def catalog_route(request):
    try:
        rows = store.read_records()
        return web.json_response({"records": rows, "meta": store.metadata()},
                                 headers={"Cache-Control": "no-store"})
    except store.GalleryError as exc:
        return _json_error(exc)


@routes.get("/ref_gallery/meta")
async def meta_route(request):
    return web.json_response(store.metadata(), headers={"Cache-Control": "no-store"})


@routes.get("/ref_gallery/assets/{kind}/{filename}")
async def asset_route(request):
    try:
        path = store.asset_path(request.match_info["kind"], request.match_info["filename"])
        return web.FileResponse(path, headers={"Cache-Control": "private, no-cache"})
    except store.GalleryError:
        raise web.HTTPNotFound()


@routes.get("/ref_gallery/gallery")
async def gallery_route(request):
    return web.FileResponse(Path(__file__).parent / "web" / "gallery.html",
                            headers={"Cache-Control": "no-cache"})


@routes.get("/ref_gallery/random")
async def random_route(request):
    try:
        category = request.query.get("category", "all")
        exclude = request.query.get("exclude_id", "")
        pool = [r for r in RandomRefGallery._candidates(category) if r["id"] != exclude] or \
               RandomRefGallery._candidates(category)
        picked = random.choice(pool)
        return web.json_response({"id": picked["id"], "name": picked["name"]},
                                 headers={"Cache-Control": "no-store"})
    except store.GalleryError as exc:
        return _json_error(exc)


@routes.post("/ref_gallery/upload")
async def upload_route(request):
    try:
        multipart = await request.multipart()
        fields, data, filename = {}, None, None
        async for part in multipart:
            if part.filename is not None:
                if part.name != "image" or data is not None:
                    raise store.GalleryError("single_image_only")
                chunks, size = [], 0
                while chunk := await part.read_chunk():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise store.GalleryError("file_too_large", 413)
                    chunks.append(chunk)
                data, filename = b"".join(chunks), part.filename
            else:
                if part.name not in {"name", "other_name", "category", "angle", "tags"} or part.name in fields:
                    raise store.GalleryError("invalid_metadata")
                chunks, size = [], 0
                while chunk := await part.read_chunk():
                    size += len(chunk)
                    if size > 2048:
                        raise store.GalleryError("invalid_metadata")
                    chunks.append(chunk)
                fields[part.name] = b"".join(chunks).decode("utf-8")
        if data is None:
            raise store.GalleryError("image_required")
        row = await asyncio.to_thread(
            store.import_image, data,
            filename=filename,
            name=fields.get("name", ""),
            other_name=fields.get("other_name", ""),
            category=fields.get("category", ""),
            angle=fields.get("angle", "unknown"),
            tags=fields.get("tags", ""),
        )
        return web.json_response(
            {"record": row, "catalog": {"records": store.read_records(), "meta": store.metadata()}},
            status=201, headers={"Cache-Control": "no-store"},
        )
    except store.GalleryError as exc:
        return _json_error(exc)
    except (ValueError, UnicodeError):
        return web.json_response({"error": "invalid_request"}, status=400)
    except OSError:
        logging.exception("ref_gallery upload failed")
        return web.json_response({"error": "storage_error"}, status=500)


@routes.post("/ref_gallery/delete")
async def delete_route(request):
    try:
        payload = await request.json()
        identity = payload.get("id") if isinstance(payload, dict) else None
        result = await asyncio.to_thread(store.delete_record, identity)
        return web.json_response(result, headers={"Cache-Control": "no-store"})
    except store.GalleryError as exc:
        return _json_error(exc)
    except (ValueError, UnicodeError):
        return web.json_response({"error": "invalid_request"}, status=400)


@routes.post("/ref_gallery/import_folder")
async def import_folder_route(request):
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise store.GalleryError("invalid_request")
        result = await asyncio.to_thread(
            store.import_folder, payload.get("folder", ""),
            category=payload.get("category", ""),
        )
        return web.json_response(result, headers={"Cache-Control": "no-store"})
    except store.GalleryError as exc:
        return _json_error(exc)
    except (ValueError, UnicodeError):
        return web.json_response({"error": "invalid_request"}, status=400)


NODE_CLASS_MAPPINGS = {
    "RefGallery": RefGallery,
    "RandomRefGallery": RandomRefGallery,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "RefGallery": "参考图库 Ref Gallery",
    "RandomRefGallery": "随机参考图 Random Ref",
}
WEB_DIRECTORY = "./web"
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
