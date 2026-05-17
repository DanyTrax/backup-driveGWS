"""Meta endpoints: permissions catalog, enum values, branding."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.permissions_catalog import (
    DEFAULT_ROLE_PERMISSIONS,
    PERMISSIONS,
    ROLE_DISPLAY,
)
from app.models.enums import UserRole
from app.services.branding_icon_service import build_branding_icon_response
from app.services.branding_storage import media_type_for_suffix, uploaded_logo_path
from app.services.branding_service import get_branding_dict

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/permissions")
async def list_permissions(_u=Depends(get_current_user)) -> dict:
    return {
        "permissions": [
            {"code": p.code, "module": p.module, "action": p.action, "description": p.description}
            for p in PERMISSIONS
        ],
        "roles": [
            {
                "code": role.value,
                "name": ROLE_DISPLAY[role][0],
                "description": ROLE_DISPLAY[role][1],
                "permissions": sorted(DEFAULT_ROLE_PERMISSIONS.get(role, frozenset())),
            }
            for role in UserRole
        ],
    }


@router.get("/branding")
async def branding(db: AsyncSession = Depends(get_db)) -> dict:
    return await get_branding_dict(db)


@router.get("/branding/logo")
async def branding_logo() -> FileResponse:
    path = uploaded_logo_path()
    if path is None or not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "logo_not_found")
    return FileResponse(
        path,
        media_type=media_type_for_suffix(path.suffix),
        filename=path.name,
    )


@router.get("/branding/icon")
async def branding_icon(
    db: AsyncSession = Depends(get_db),
    fmt: Literal["png", "webp", "svg", "original"] = Query(
        "png",
        description="png (favicon raster), webp, svg (PNG embebido en SVG), original sin redimensionar",
    ),
) -> Response:
    try:
        body, media = await build_branding_icon_response(db, fmt=fmt)
    except ValueError as exc:
        code = str(exc)
        if code == "no_logo":
            return RedirectResponse(url="/favicon.svg", status_code=302)
        if code == "svg_source_use_original":
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "El logo es SVG vectorial: usá fmt=original o fmt=svg.",
            ) from exc
        if code == "logo_fetch_failed":
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                "No se pudo descargar la URL del logo.",
            ) from exc
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=code) from exc
    return Response(
        content=body,
        media_type=media,
        headers={"Cache-Control": "public, max-age=3600"},
    )
