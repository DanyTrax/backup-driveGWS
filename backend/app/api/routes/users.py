"""Platform user management (SuperAdmin / Operator per permission)."""
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
    require_permission,
)
from app.core.security import hash_password
from app.models.accounts import GwAccount
from app.models.enums import AuditAction
from app.models.mailbox_delegation import SysUserMailboxDelegation
from app.models.vault_drive_delegation import SysUserVaultDriveDelegation
from app.models.users import SysRole, SysUser
from app.schemas.users import (
    AdminPasswordReset,
    MailboxDelegationsPut,
    UserCreate,
    UserOut,
    UserUpdate,
    VaultDriveDelegationsPut,
)
from app.services.audit_service import record_audit

router = APIRouter(prefix="/users", tags=["users"])


async def _load_role(db: AsyncSession, code: str) -> SysRole:
    stmt = select(SysRole).where(SysRole.code == code)
    role = (await db.execute(stmt)).scalar_one_or_none()
    if role is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unknown_role:{code}")
    return role


def _to_out(u: SysUser) -> UserOut:
    rn = None
    if u.role is not None:
        rn = u.role.name
    return UserOut(
        id=str(u.id),
        email=u.email,
        full_name=u.full_name,
        role_code=u.role_code,
        role_name=rn,
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
    stmt = select(SysUser).options(selectinload(SysUser.role)).order_by(SysUser.created_at.desc())
    rows = (await db.execute(stmt)).scalars().all()
    return [_to_out(u) for u in rows]


@router.get("/{user_id}/mailbox-delegations", response_model=list[str])
async def list_user_mailbox_delegations(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _viewer: SysUser = Depends(require_permission("users.view")),
) -> list[str]:
    target = (await db.execute(select(SysUser).where(SysUser.id == user_id))).scalar_one_or_none()
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    stmt = select(SysUserMailboxDelegation.gw_account_id).where(
        SysUserMailboxDelegation.sys_user_id == user_id
    )
    rows = (await db.execute(stmt)).scalars().all()
    return sorted(str(r) for r in rows)


@router.put("/{user_id}/mailbox-delegations", response_model=list[str])
async def put_user_mailbox_delegations(
    user_id: uuid.UUID,
    payload: MailboxDelegationsPut,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("mailbox.delegate")),
) -> list[str]:
    target = (await db.execute(select(SysUser).where(SysUser.id == user_id))).scalar_one_or_none()
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")

    ids = list(dict.fromkeys(payload.account_ids))
    if ids:
        cnt = (
            await db.execute(select(func.count()).select_from(GwAccount).where(GwAccount.id.in_(ids)))
        ).scalar_one()
        if int(cnt) != len(ids):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "unknown_account_id")

    await db.execute(delete(SysUserMailboxDelegation).where(SysUserMailboxDelegation.sys_user_id == user_id))
    for aid in ids:
        db.add(
            SysUserMailboxDelegation(
                sys_user_id=user_id,
                gw_account_id=aid,
                granted_by_user_id=current.id,
            )
        )

    await record_audit(
        db,
        action=AuditAction.USER_UPDATED,
        actor_user_id=current.id,
        actor_label=current.email,
        target_table="sys_users",
        target_id=str(user_id),
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        message="mailbox_delegations_updated",
        metadata={"account_ids": [str(x) for x in ids]},
    )
    await db.commit()
    return sorted(str(x) for x in ids)


@router.get("/{user_id}/vault-drive-delegations", response_model=list[str])
async def list_user_vault_drive_delegations(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _viewer: SysUser = Depends(require_permission("users.view")),
) -> list[str]:
    target = (await db.execute(select(SysUser).where(SysUser.id == user_id))).scalar_one_or_none()
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    stmt = select(SysUserVaultDriveDelegation.gw_account_id).where(
        SysUserVaultDriveDelegation.sys_user_id == user_id
    )
    rows = (await db.execute(stmt)).scalars().all()
    return sorted(str(r) for r in rows)


@router.put("/{user_id}/vault-drive-delegations", response_model=list[str])
async def put_user_vault_drive_delegations(
    user_id: uuid.UUID,
    payload: VaultDriveDelegationsPut,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("vault_drive.delegate")),
) -> list[str]:
    target = (await db.execute(select(SysUser).where(SysUser.id == user_id))).scalar_one_or_none()
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")

    ids = list(dict.fromkeys(payload.account_ids))
    if ids:
        cnt = (
            await db.execute(select(func.count()).select_from(GwAccount).where(GwAccount.id.in_(ids)))
        ).scalar_one()
        if int(cnt) != len(ids):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "unknown_account_id")

    await db.execute(
        delete(SysUserVaultDriveDelegation).where(SysUserVaultDriveDelegation.sys_user_id == user_id)
    )
    for aid in ids:
        db.add(
            SysUserVaultDriveDelegation(
                sys_user_id=user_id,
                gw_account_id=aid,
                granted_by_user_id=current.id,
            )
        )

    await record_audit(
        db,
        action=AuditAction.USER_UPDATED,
        actor_user_id=current.id,
        actor_label=current.email,
        target_table="sys_users",
        target_id=str(user_id),
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        message="vault_drive_delegations_updated",
        metadata={"account_ids": [str(x) for x in ids]},
    )
    await db.commit()
    return sorted(str(x) for x in ids)


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

    role = await _load_role(db, payload.role_code)
    user = SysUser(
        email=payload.email.lower(),
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role_id=role.id,
        role_code=role.code,
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
    reloaded = (
        await db.execute(
            select(SysUser).options(selectinload(SysUser.role)).where(SysUser.id == user.id)
        )
    ).scalar_one()
    return _to_out(reloaded)


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
        # Solo SuperAdmin puede promover/degradar otro SuperAdmin.
        if (
            user.role_code == "super_admin"
            or payload.role_code == "super_admin"
        ) and current.role_code != "super_admin":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "requires_superadmin")
        role = await _load_role(db, payload.role_code)
        user.role_id = role.id
        user.role_code = role.code

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
    response_model=None,
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
    response_model=None,
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
    if user.role_code == "super_admin":
        admins = await db.execute(
            select(func.count())
            .select_from(SysUser)
            .where(SysUser.role_code == "super_admin")
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
