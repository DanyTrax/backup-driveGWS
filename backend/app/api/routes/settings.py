"""System settings CRUD (key-value)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_client_ip,
    get_db,
    get_user_agent,
    require_permission,
)
from app.models.enums import AuditAction
from app.models.settings import SysSetting
from app.models.users import SysUser
from app.schemas.branding import BrandingConfigOut, BrandingUpdate
from app.schemas.mail_purge import PurgeAllLocalMailIn, PurgeAllLocalMailOut
from app.services.audit_service import record_audit
from app.services.branding_storage import (
    BRANDING_DIR,
    MAX_LOGO_BYTES,
    ALLOWED_LOGO_SUFFIXES,
    delete_uploaded_logo,
    guess_suffix,
)
from app.services.branding_service import get_branding_config_for_editor, get_branding_dict
from app.services.mail_purge_service import (
    PURGE_ALL_MAIL_LOCAL_CONFIRM_PHRASE,
    purge_all_local_mail_data,
)
from app.services.settings_service import set_value

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingOut(BaseModel):
    key: str
    value: str | None
    category: str
    is_secret: bool
    description: str | None


class SettingIn(BaseModel):
    key: str
    value: str | None
    is_secret: bool = False
    category: str = "general"
    description: str | None = None


@router.get("/branding-config", response_model=BrandingConfigOut)
async def get_branding_config(
    db: AsyncSession = Depends(get_db),
    _u: SysUser = Depends(require_permission("settings.view")),
) -> BrandingConfigOut:
    raw = await get_branding_config_for_editor(db)
    return BrandingConfigOut(
        app_name=str(raw["app_name"]),
        primary_color=str(raw["primary_color"]),
        accent_color=str(raw["accent_color"]),
        logo_url_external=str(raw["logo_url_external"]),
        has_uploaded_logo=bool(raw["has_uploaded_logo"]),
    )


@router.put("/branding", response_model=dict)
async def update_branding(
    payload: BrandingUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("settings.branding")),
) -> dict:
    updates: dict[str, str | None] = {}
    if payload.app_name is not None:
        updates["branding.app_name"] = payload.app_name.strip() or None
    if payload.primary_color is not None:
        updates["branding.primary_color"] = payload.primary_color or None
    if payload.accent_color is not None:
        updates["branding.accent_color"] = payload.accent_color or None
    if payload.logo_url is not None:
        lu = payload.logo_url.strip()
        updates["branding.logo_url"] = lu if lu else None
        if lu.startswith("http://") or lu.startswith("https://") or lu.startswith("/"):
            delete_uploaded_logo()

    for key, val in updates.items():
        short = key.replace("branding.", "")
        await set_value(
            db,
            key,
            val,
            is_secret=False,
            category="branding",
            description=f"Branding: {short}",
            actor_user_id=str(current.id),
        )

    if updates:
        await record_audit(
            db,
            action=AuditAction.SETTING_CHANGED,
            actor_user_id=current.id,
            actor_label=current.email,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
            target_table="sys_settings",
            target_id="branding",
            metadata={"keys": list(updates.keys())},
        )
    await db.commit()
    return await get_branding_dict(db)


@router.post("/branding/logo")
async def upload_branding_logo(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("settings.branding")),
    file: UploadFile = File(...),
) -> dict:
    if not file.filename:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "missing_filename")
    suffix = guess_suffix(file.filename)
    if suffix not in ALLOWED_LOGO_SUFFIXES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"tipo_no_permitido: use {', '.join(sorted(ALLOWED_LOGO_SUFFIXES))}",
        )
    body = await file.read()
    if len(body) > MAX_LOGO_BYTES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "archivo_demasiado_grande")
    BRANDING_DIR.mkdir(parents=True, exist_ok=True)
    delete_uploaded_logo()
    dest = BRANDING_DIR / f"logo{suffix}"
    with dest.open("wb") as out:
        out.write(body)

    await set_value(
        db,
        "branding.logo_url",
        "",
        is_secret=False,
        category="branding",
        description="Branding: logo URL vacío (logo subido en disco)",
        actor_user_id=str(current.id),
    )
    await record_audit(
        db,
        action=AuditAction.SETTING_CHANGED,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        target_table="sys_settings",
        target_id="branding.logo_upload",
    )
    await db.commit()
    return await get_branding_dict(db)


@router.delete("/branding/logo")
async def delete_branding_logo_file(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("settings.branding")),
) -> dict:
    delete_uploaded_logo()
    await record_audit(
        db,
        action=AuditAction.SETTING_CHANGED,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        target_table="sys_settings",
        target_id="branding.logo_delete_file",
    )
    await db.commit()
    return await get_branding_dict(db)


@router.get("", response_model=list[SettingOut])
async def list_settings(
    category: str | None = None,
    db: AsyncSession = Depends(get_db),
    _u: SysUser = Depends(require_permission("settings.view")),
) -> list[SettingOut]:
    stmt = select(SysSetting).order_by(SysSetting.category, SysSetting.key)
    if category:
        stmt = stmt.where(SysSetting.category == category)
    rows = (await db.execute(stmt)).scalars().all()
    return [
        SettingOut(
            key=r.key,
            value=None if r.is_secret else r.value,
            category=r.category,
            is_secret=r.is_secret,
            description=r.description,
        )
        for r in rows
    ]


@router.put("", response_model=SettingOut)
async def upsert_setting(
    payload: SettingIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("settings.edit")),
) -> SettingOut:
    row = await set_value(
        db,
        payload.key,
        payload.value,
        is_secret=payload.is_secret,
        category=payload.category,
        description=payload.description,
        actor_user_id=str(current.id),
    )
    await record_audit(
        db,
        action=AuditAction.SETTING_CHANGED,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        target_table="sys_settings",
        target_id=payload.key,
    )
    await db.commit()
    return SettingOut(
        key=row.key,
        value=None if row.is_secret else row.value,
        category=row.category,
        is_secret=row.is_secret,
        description=row.description,
    )


@router.post("/purge-all-local-mail", response_model=PurgeAllLocalMailOut)
async def purge_all_local_mail(
    payload: PurgeAllLocalMailIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("platform.purge_all_mail_local")),
) -> PurgeAllLocalMailOut:
    """Elimina en todas las cuentas Workspace: Maildir, trabajo GYB local, filas de log de backup Gmail y tokens webmail.

    No borra usuarios de plataforma ni filas ``gw_accounts``. No elimina correo ni archivos en la nube.
    Requiere frase de confirmación exacta en el cuerpo.
    """
    if payload.confirmation.strip() != PURGE_ALL_MAIL_LOCAL_CONFIRM_PHRASE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_confirmation")

    stats = await purge_all_local_mail_data(db)
    await record_audit(
        db,
        action=AuditAction.MAIL_DATA_PURGED,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        target_table="platform",
        message="purge_all_local_mail",
        metadata=dict(stats),
    )
    await db.commit()
    return PurgeAllLocalMailOut(**stats)
