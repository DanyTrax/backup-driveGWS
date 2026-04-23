"""Platform user management (SuperAdmin / Operator per permission)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import (
    get_client_ip,
    get_current_user,
    get_db,
    get_user_agent,
    require_permission,
)
from app.core.security import hash_password
from app.models.enums import AuditAction, UserRole
from app.models.users import SysRole, SysUser
from app.schemas.users import AdminPasswordReset, UserCreate, UserOut, UserUpdate
from app.services.audit_service import record_audit

router = APIRouter(prefix="/users", tags=["users"])


async def _load_role(db: AsyncSession, code: str) -> SysRole:
    stmt = select(SysRole).where(SysRole.code == code)
    role = (await db.execute(stmt)).scalar_one_or_none()
    if role is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unknown_role:{code}")
    return role


def _to_out(u: SysUser) -> UserOut:
    return UserOut(
        id=str(u.id),
        email=u.email,
        full_name=u.full_name,
        role_code=u.role_code,
        status=u.status,
        mfa_enabled=u.mfa_enabled,
        last_login_at=u.last_login_at,
        failed_login_count=u.failed_login_count,
        locked_until=u.locked_until,
        created_at=u.created_at,
    )


@router.get("", response_model=list[UserOut])
async def list_users(
    db: AsyncSession = Depends(get_db),
    _user: SysUser = Depends(require_permission("users.view")),
) -> list[UserOut]:
    stmt = select(SysUser).order_by(SysUser.created_at.desc())
    rows = (await db.execute(stmt)).scalars().all()
    return [_to_out(u) for u in rows]


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("users.create")),
) -> UserOut:
    exists = await db.execute(select(func.count()).where(SysUser.email == payload.email.lower()))
    if exists.scalar_one() > 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "email_already_exists")

    role = await _load_role(db, payload.role_code.value)
    user = SysUser(
        email=payload.email.lower(),
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role_id=role.id,
        role_code=payload.role_code.value,
        must_change_password=payload.must_change_password,
    )
    db.add(user)
    await db.flush()

    await record_audit(
        db,
        action=AuditAction.USER_CREATED,
        actor_user_id=current.id,
        actor_label=current.email,
        target_table="sys_users",
        target_id=str(user.id),
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        metadata={"email": user.email, "role": user.role_code},
    )
    await db.commit()
    await db.refresh(user)
    return _to_out(user)


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("users.edit")),
) -> UserOut:
    user = (
        await db.execute(
            select(SysUser).options(selectinload(SysUser.role)).where(SysUser.id == user_id)
        )
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")

    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.preferred_locale is not None:
        user.preferred_locale = payload.preferred_locale
    if payload.preferred_timezone is not None:
        user.preferred_timezone = payload.preferred_timezone
    if payload.status is not None:
        user.status = payload.status.value
    if payload.role_code is not None:
        # Only SuperAdmin may promote/demote another SuperAdmin.
        if (
            user.role_code == UserRole.SUPER_ADMIN.value
            or payload.role_code == UserRole.SUPER_ADMIN
        ) and current.role_code != UserRole.SUPER_ADMIN.value:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "requires_superadmin")
        role = await _load_role(db, payload.role_code.value)
        user.role_id = role.id
        user.role_code = payload.role_code.value

    await record_audit(
        db,
        action=AuditAction.USER_UPDATED,
        actor_user_id=current.id,
        actor_label=current.email,
        target_table="sys_users",
        target_id=str(user.id),
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        metadata=payload.model_dump(exclude_none=True),
    )
    await db.commit()
    await db.refresh(user)
    return _to_out(user)


@router.post(
    "/{user_id}/password",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def admin_reset_password(
    user_id: uuid.UUID,
    payload: AdminPasswordReset,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("users.reset_password")),
) -> None:
    user = (await db.execute(select(SysUser).where(SysUser.id == user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = payload.must_change_password
    user.failed_login_count = 0
    user.locked_until = None

    await record_audit(
        db,
        action=AuditAction.USER_UPDATED,
        actor_user_id=current.id,
        actor_label=current.email,
        target_table="sys_users",
        target_id=str(user.id),
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        message="admin_password_reset",
    )
    await db.commit()


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_user(
    user_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("users.delete")),
) -> None:
    if str(user_id) == str(current.id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "cannot_delete_self")
    user = (await db.execute(select(SysUser).where(SysUser.id == user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    # Prevent removing the last SuperAdmin.
    if user.role_code == UserRole.SUPER_ADMIN.value:
        admins = await db.execute(
            select(func.count())
            .select_from(SysUser)
            .where(SysUser.role_code == UserRole.SUPER_ADMIN.value)
        )
        if admins.scalar_one() <= 1:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "last_superadmin")

    await record_audit(
        db,
        action=AuditAction.USER_DELETED,
        actor_user_id=current.id,
        actor_label=current.email,
        target_table="sys_users",
        target_id=str(user.id),
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )
    await db.delete(user)
    await db.commit()
