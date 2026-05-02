"""Gestión de roles personalizados (sys_roles / sys_permissions)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import (
    get_client_ip,
    get_db,
    get_user_agent,
    require_any_permission,
    require_permission,
)
from app.models.enums import AuditAction
from app.models.users import SysPermission, SysRole, SysUser
from app.schemas.roles import PermissionBrief, RoleCreate, RoleOut, RoleUpdate
from app.services.audit_service import record_audit

router = APIRouter(prefix="/roles", tags=["roles"])


def _can_list_roles():
    return require_any_permission("roles.view", "roles.manage", "users.create", "users.edit")


def _role_to_out(r: SysRole) -> RoleOut:
    perms = sorted((r.permissions or []), key=lambda p: p.code)
    return RoleOut(
        id=str(r.id),
        code=r.code,
        name=r.name,
        description=r.description,
        is_system=r.is_system,
        permissions=[
            PermissionBrief(
                code=p.code,
                module=p.module,
                action=p.action,
                description=p.description,
            )
            for p in perms
        ],
    )


@router.get("", response_model=list[RoleOut])
async def list_roles(
    db: AsyncSession = Depends(get_db),
    _u: SysUser = Depends(_can_list_roles()),
) -> list[RoleOut]:
    stmt = (
        select(SysRole)
        .options(selectinload(SysRole.permissions))
        .order_by(SysRole.is_system.desc(), SysRole.code.asc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [_role_to_out(r) for r in rows]


@router.post("", response_model=RoleOut, status_code=status.HTTP_201_CREATED)
async def create_role(
    payload: RoleCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("roles.manage")),
) -> RoleOut:
    exists = (
        await db.execute(select(func.count()).select_from(SysRole).where(SysRole.code == payload.code))
    ).scalar_one()
    if int(exists) > 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "role_code_exists")

    codes = list(dict.fromkeys(payload.permission_codes))
    if codes:
        cnt = (
            await db.execute(
                select(func.count()).select_from(SysPermission).where(SysPermission.code.in_(codes))
            )
        ).scalar_one()
        if int(cnt) != len(codes):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "unknown_permission_code")

    role = SysRole(
        code=payload.code,
        name=payload.name,
        description=payload.description,
        is_system=False,
    )
    if codes:
        pr = (
            await db.execute(select(SysPermission).where(SysPermission.code.in_(codes)))
        ).scalars().all()
        role.permissions = list(pr)
    db.add(role)
    await db.flush()

    await record_audit(
        db,
        action=AuditAction.SETTING_CHANGED,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        target_table="sys_roles",
        target_id=str(role.id),
        message="role_created",
        metadata={"code": role.code, "permissions": codes},
    )
    await db.commit()
    await db.refresh(role)
    stmt = (
        select(SysRole)
        .options(selectinload(SysRole.permissions))
        .where(SysRole.id == role.id)
    )
    r2 = (await db.execute(stmt)).scalar_one()
    return _role_to_out(r2)


@router.patch("/{role_id}", response_model=RoleOut)
async def update_role(
    role_id: uuid.UUID,
    payload: RoleUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("roles.manage")),
) -> RoleOut:
    role = (
        await db.execute(
            select(SysRole)
            .options(selectinload(SysRole.permissions))
            .where(SysRole.id == role_id)
        )
    ).scalar_one_or_none()
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role_not_found")
    if role.is_system:
        raise HTTPException(status.HTTP_409_CONFLICT, "cannot_edit_system_role")

    if payload.name is not None:
        role.name = payload.name
    if payload.description is not None:
        role.description = payload.description
    if payload.permission_codes is not None:
        codes = list(dict.fromkeys(payload.permission_codes))
        if codes:
            cnt = (
                await db.execute(
                    select(func.count()).select_from(SysPermission).where(SysPermission.code.in_(codes))
                )
            ).scalar_one()
            if int(cnt) != len(codes):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "unknown_permission_code")
            pr = (
                await db.execute(select(SysPermission).where(SysPermission.code.in_(codes)))
            ).scalars().all()
            role.permissions = list(pr)
        else:
            role.permissions = []

    await record_audit(
        db,
        action=AuditAction.SETTING_CHANGED,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        target_table="sys_roles",
        target_id=str(role.id),
        message="role_updated",
        metadata=payload.model_dump(exclude_none=True),
    )
    await db.commit()
    await db.refresh(role)
    stmt = (
        select(SysRole)
        .options(selectinload(SysRole.permissions))
        .where(SysRole.id == role_id)
    )
    r2 = (await db.execute(stmt)).scalar_one()
    return _role_to_out(r2)


@router.delete(
    "/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def delete_role(
    role_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("roles.manage")),
) -> None:
    role = (await db.execute(select(SysRole).where(SysRole.id == role_id))).scalar_one_or_none()
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role_not_found")
    if role.is_system:
        raise HTTPException(status.HTTP_409_CONFLICT, "cannot_delete_system_role")

    n_users = (
        await db.execute(select(func.count()).select_from(SysUser).where(SysUser.role_id == role_id))
    ).scalar_one()
    if int(n_users) > 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "role_in_use")

    await record_audit(
        db,
        action=AuditAction.SETTING_CHANGED,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        target_table="sys_roles",
        target_id=str(role.id),
        message="role_deleted",
        metadata={"code": role.code},
    )
    await db.execute(delete(SysRole).where(SysRole.id == role_id))
    await db.commit()
