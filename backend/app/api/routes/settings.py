"""System settings CRUD (key-value)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
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
from app.services.audit_service import record_audit
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
