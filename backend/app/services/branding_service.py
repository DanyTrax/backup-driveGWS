"""Valores públicos de branding (nombre, colores, logo efectivo)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.settings import SysSetting
from app.services.branding_storage import has_uploaded_logo


async def get_branding_dict(db: AsyncSession) -> dict[str, str]:
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
    raw_logo = (out.get("logo_url") or "").strip()
    if raw_logo.startswith("http://") or raw_logo.startswith("https://") or raw_logo.startswith("/"):
        out["logo_url"] = raw_logo
    elif has_uploaded_logo():
        out["logo_url"] = "/api/meta/branding/logo"
    else:
        out["logo_url"] = ""
    return out


async def get_branding_config_for_editor(db: AsyncSession) -> dict[str, str | bool]:
    """Valores crudos + flag de archivo para el formulario de configuración."""
    rows = (
        await db.execute(
            select(SysSetting).where(SysSetting.key.like("branding.%"))
        )
    ).scalars().all()
    raw: dict[str, str] = {}
    for r in rows:
        if r.is_secret:
            continue
        raw[r.key.replace("branding.", "")] = r.value or ""
    return {
        "app_name": raw.get("app_name") or "MSA Backup Commander",
        "primary_color": raw.get("primary_color") or "#1d4ed8",
        "accent_color": raw.get("accent_color") or "#0ea5e9",
        "logo_url_external": raw.get("logo_url") or "",
        "has_uploaded_logo": has_uploaded_logo(),
    }
