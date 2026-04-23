"""Meta endpoints: permissions catalog, enum values, branding."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.permissions_catalog import (
    DEFAULT_ROLE_PERMISSIONS,
    PERMISSIONS,
    ROLE_DISPLAY,
)
from app.models.enums import UserRole
from app.models.settings import SysSetting

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
    rows = (
        await db.execute(
            select(SysSetting).where(SysSetting.key.like("branding.%"))
        )
    ).scalars().all()
    out: dict[str, str] = {}
    for r in rows:
        if r.is_secret:
            continue
        out[r.key.replace("branding.", "")] = r.value or ""
    out.setdefault("app_name", "MSA Backup Commander")
    out.setdefault("primary_color", "#1d4ed8")
    out.setdefault("accent_color", "#0ea5e9")
    out.setdefault("logo_url", "")
    return out
