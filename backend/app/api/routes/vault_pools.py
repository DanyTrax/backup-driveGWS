"""Pools de bóveda (Shared Drives adicionales) y asignación por cuenta."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_db, get_user_agent, require_permission
from app.models.accounts import GwAccount
from app.models.enums import AuditAction
from app.models.users import SysUser
from app.schemas.vault_pools import (
    AccountVaultAssignmentIn,
    AccountVaultAssignmentOut,
    VaultPoolCreateIn,
    VaultPoolOut,
    VaultPoolProvisionIn,
    VaultPoolUpdateIn,
)
from app.services.audit_service import record_audit
from app.services.vault_assignment_service import (
    VaultAssignmentError,
    apply_vault_assignment,
    load_account_with_vault_pool,
    resolve_vault_target,
)
from app.services.vault_pool_store import (
    create_pool,
    delete_pool,
    get_pool,
    list_pools,
    provision_pool_in_google,
    update_pool,
)

router = APIRouter(prefix="/vault-pools", tags=["vault-pools"])


def _pool_out(pool, account_count: int) -> VaultPoolOut:
    return VaultPoolOut(
        id=str(pool.id),
        name=pool.name,
        shared_drive_id=pool.shared_drive_id,
        root_folder_id=pool.root_folder_id,
        description=pool.description,
        account_count=account_count,
        created_at=pool.created_at,
    )


@router.get("", response_model=list[VaultPoolOut])
async def list_vault_pools(
    db: AsyncSession = Depends(get_db),
    _u: SysUser = Depends(require_permission("settings.view")),
) -> list[VaultPoolOut]:
    rows = await list_pools(db)
    return [_pool_out(p, cnt) for p, cnt in rows]


@router.post("/provision", response_model=VaultPoolOut, status_code=status.HTTP_201_CREATED)
async def provision_vault_pool(
    payload: VaultPoolProvisionIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("settings.edit")),
) -> VaultPoolOut:
    """Crea la unidad compartida en Google, la SA como Manager y BackupRoot; registra el pool."""
    try:
        row = await provision_pool_in_google(
            db,
            name=payload.name,
            description=payload.description,
            root_folder_name=payload.root_folder_name,
            drive_display_name=payload.drive_display_name,
        )
    except ValueError as exc:
        msg = str(exc)
        if msg == "duplicate_name":
            raise HTTPException(status.HTTP_409_CONFLICT, detail="duplicate_name") from exc
        if msg.startswith("google_shared_drive_create_failed"):
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                detail={"error": msg, "message": "Google no permitió crear la unidad compartida."},
            ) from exc
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=msg) from exc

    await record_audit(
        db,
        action=AuditAction.SETTING_CHANGED,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        target_table="vault_pools",
        target_id=str(row.id),
        message="vault_pool_provisioned",
        metadata={
            "name": row.name,
            "shared_drive_id": row.shared_drive_id,
            "root_folder_id": row.root_folder_id,
        },
    )
    await db.commit()
    return _pool_out(row, 0)


@router.post("", response_model=VaultPoolOut, status_code=status.HTTP_201_CREATED)
async def add_vault_pool(
    payload: VaultPoolCreateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("settings.edit")),
) -> VaultPoolOut:
    try:
        row = await create_pool(
            db,
            name=payload.name,
            shared_drive_id=payload.shared_drive_id,
            root_folder_id=payload.root_folder_id,
            description=payload.description,
        )
    except ValueError as exc:
        msg = str(exc)
        if msg == "duplicate_name":
            raise HTTPException(status.HTTP_409_CONFLICT, detail="duplicate_name") from exc
        if msg == "shared_drive_not_accessible":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=msg) from exc
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=msg) from exc

    await record_audit(
        db,
        action=AuditAction.SETTING_CHANGED,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        target_table="vault_pools",
        target_id=str(row.id),
        message="vault_pool_created",
        metadata={"name": row.name, "shared_drive_id": row.shared_drive_id},
    )
    await db.commit()
    return _pool_out(row, 0)


@router.patch("/{pool_id}", response_model=VaultPoolOut)
async def patch_vault_pool(
    pool_id: str,
    payload: VaultPoolUpdateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("settings.edit")),
) -> VaultPoolOut:
    try:
        pid = uuid.UUID(pool_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="invalid_id") from exc
    pool = await get_pool(db, pid)
    if pool is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="pool_not_found")
    try:
        row = await update_pool(
            db,
            pool,
            name=payload.name,
            shared_drive_id=payload.shared_drive_id,
            root_folder_id=payload.root_folder_id,
            description=payload.description,
        )
    except ValueError as exc:
        msg = str(exc)
        if msg == "duplicate_name":
            raise HTTPException(status.HTTP_409_CONFLICT, detail=msg) from exc
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=msg) from exc
    await record_audit(
        db,
        action=AuditAction.SETTING_CHANGED,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        target_table="vault_pools",
        target_id=str(row.id),
        message="vault_pool_updated",
    )
    await db.commit()
    cnt = int(
        (
            await db.execute(
                select(func.count()).select_from(GwAccount).where(GwAccount.vault_pool_id == row.id)
            )
        ).scalar_one()
    )
    return _pool_out(row, cnt)


@router.delete(
    "/{pool_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def remove_vault_pool(
    pool_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("settings.edit")),
) -> None:
    try:
        pid = uuid.UUID(pool_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="invalid_id") from exc
    try:
        ok = await delete_pool(db, pid)
    except ValueError as exc:
        if str(exc) == "pool_in_use":
            raise HTTPException(status.HTTP_409_CONFLICT, detail="pool_in_use") from exc
        raise
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="pool_not_found")
    await record_audit(
        db,
        action=AuditAction.SETTING_CHANGED,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        target_table="vault_pools",
        target_id=pool_id,
        message="vault_pool_deleted",
    )
    await db.commit()


@router.put("/accounts/{account_id}/vault-assignment", response_model=AccountVaultAssignmentOut)
async def set_account_vault_assignment(
    account_id: str,
    payload: AccountVaultAssignmentIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("accounts.edit")),
) -> AccountVaultAssignmentOut:
    try:
        aid = uuid.UUID(account_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="invalid_id") from exc

    acc = await load_account_with_vault_pool(db, aid)
    if acc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="account_not_found")

    pool_uuid: uuid.UUID | None = None
    if payload.vault_pool_id:
        try:
            pool_uuid = uuid.UUID(payload.vault_pool_id)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="invalid_pool_id") from exc

    try:
        await apply_vault_assignment(
            db,
            acc,
            vault_mode=payload.vault_mode,
            vault_pool_id=pool_uuid,
            reprovision=payload.reprovision,
        )
    except VaultAssignmentError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    target = await resolve_vault_target(db, acc)
    await record_audit(
        db,
        action=AuditAction.SETTING_CHANGED,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        target_table="gw_accounts",
        target_id=str(acc.id),
        message="account_vault_assignment_changed",
        metadata={
            "email": acc.email,
            "vault_mode": acc.vault_mode,
            "vault_pool_id": str(acc.vault_pool_id) if acc.vault_pool_id else None,
            "dedicated_shared_drive_id": acc.dedicated_shared_drive_id,
        },
    )
    await db.commit()
    await db.refresh(acc)
    if acc.vault_pool:
        await db.refresh(acc, attribute_names=["vault_pool"])

    return AccountVaultAssignmentOut(
        account_id=str(acc.id),
        email=acc.email,
        vault_mode=acc.vault_mode,
        vault_pool_id=str(acc.vault_pool_id) if acc.vault_pool_id else None,
        vault_pool_name=acc.vault_pool.name if acc.vault_pool else None,
        dedicated_shared_drive_id=acc.dedicated_shared_drive_id,
        drive_vault_folder_id=acc.drive_vault_folder_id,
        vault_label=target.label,
    )
