"""Genera iconos (favicon) normalizados desde el logo de branding (URL o archivo subido)."""
from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Literal

import httpx
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.branding_service import get_branding_dict
from app.services.branding_storage import uploaded_logo_path

# Máximo al descargar por URL (evita OOM / SSRF abusiva desde panel).
MAX_FETCH_BYTES = 6 * 1024 * 1024

IconFmt = Literal["png", "webp", "svg", "original"]

_MEDIA_FROM_PIL: dict[str, str] = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "WEBP": "image/webp",
    "GIF": "image/gif",
}


def _static_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "static"


async def _load_raw_logo(db: AsyncSession) -> tuple[bytes, str]:
    """Devuelve bytes del logo y un sufijo aproximado (.png, .jpg, …)."""
    data = await get_branding_dict(db)
    url = (data.get("logo_url") or "").strip()
    if not url:
        raise ValueError("no_logo")

    if url.startswith("/api/meta/branding/logo"):
        path = uploaded_logo_path()
        if path is None or not path.is_file():
            raise ValueError("no_logo")
        return path.read_bytes(), path.suffix.lower() or ".png"

    if url.startswith("https://") or url.startswith("http://"):
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(20.0),
            follow_redirects=True,
            limits=httpx.Limits(max_connections=5),
        ) as client:
            r = await client.get(url)
            r.raise_for_status()
            ct = (r.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
            if not ct.startswith("image/"):
                raise ValueError("not_image")
            body = r.content
            if len(body) > MAX_FETCH_BYTES:
                raise ValueError("too_large")
            if ct == "image/jpeg":
                return body, ".jpg"
            if ct == "image/png":
                return body, ".png"
            if ct == "image/webp":
                return body, ".webp"
            if ct == "image/gif":
                return body, ".gif"
            if ct == "image/svg+xml":
                return body, ".svg"
            return body, ".png"

    if url.startswith("/") and not url.startswith("//"):
        static = _static_dir()
        rel = url.lstrip("/").replace("..", "")
        candidate = (static / rel).resolve()
        try:
            candidate.relative_to(static.resolve())
        except ValueError as exc:
            raise ValueError("invalid_local_logo_path") from exc
        if not candidate.is_file():
            raise ValueError("local_logo_not_found")
        return candidate.read_bytes(), candidate.suffix.lower() or ".png"

    raise ValueError("unsupported_logo_source")


def _is_svg_bytes(raw: bytes) -> bool:
    head = raw.lstrip()[:256]
    return head.startswith(b"<svg") or head.startswith(b"<?xml")


def _raster_thumbnail(raw: bytes, *, max_px: int) -> Image.Image:
    im = Image.open(io.BytesIO(raw))
    im = im.convert("RGBA")
    im.thumbnail((max_px, max_px), Image.Resampling.LANCZOS)
    return im


def render_png(raw: bytes, *, max_px: int = 256) -> bytes:
    im = _raster_thumbnail(raw, max_px=max_px)
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def render_webp(raw: bytes, *, max_px: int = 256) -> bytes:
    im = _raster_thumbnail(raw, max_px=max_px)
    buf = io.BytesIO()
    im.save(buf, format="WEBP", quality=88, method=4)
    return buf.getvalue()


def render_svg_wrapped_png(raw: bytes, *, embed_px: int = 96) -> bytes:
    png = render_png(raw, max_px=embed_px)
    b64 = base64.b64encode(png).decode("ascii")
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{embed_px}" height="{embed_px}" viewBox="0 0 {embed_px} {embed_px}">'
        f'<image width="{embed_px}" height="{embed_px}" '
        f'href="data:image/png;base64,{b64}"/></svg>'
    )
    return svg.encode("utf-8")


def sniff_media_type(raw: bytes) -> str | None:
    try:
        im = Image.open(io.BytesIO(raw))
        fmt = (im.format or "").upper()
        if fmt == "JPEG":
            return "image/jpeg"
        return _MEDIA_FROM_PIL.get(fmt)
    except Exception:  # noqa: BLE001
        if _is_svg_bytes(raw):
            return "image/svg+xml"
        return None


async def build_branding_icon_response(
    db: AsyncSession, *, fmt: IconFmt
) -> tuple[bytes, str]:
    """Devuelve (cuerpo, content_type)."""
    try:
        raw, _sfx = await _load_raw_logo(db)
    except httpx.HTTPError as exc:
        raise ValueError("logo_fetch_failed") from exc

    if fmt == "original":
        mt = sniff_media_type(raw) or "application/octet-stream"
        return raw, mt

    if _is_svg_bytes(raw):
        if fmt == "svg":
            return raw, "image/svg+xml"
        raise ValueError("svg_source_use_original")

    if fmt == "png":
        return render_png(raw), "image/png"
    if fmt == "webp":
        try:
            return render_webp(raw), "image/webp"
        except Exception:
            return render_png(raw), "image/png"
    if fmt == "svg":
        return render_svg_wrapped_png(raw), "image/svg+xml"

    raise ValueError("bad_format")
