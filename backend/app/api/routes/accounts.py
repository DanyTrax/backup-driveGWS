"""Google Workspace account listing, opt-in and sync."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_client_ip,
    get_current_user,
    get_db,
    get_user_agent,
    require_permission,
)
from app.models.accounts import GwAccount
from app.models.enums import AuditAction
from app.models.users import SysUser
from app.schemas.accounts import AccountApproveIn, AccountOut, AccountRevokeIn, SyncOut
from app.services.accounts_service import (
    approve_account,
    revoke_account,
    sync_workspace_directory,
)
from app.services.audit_service import record_audit

router = APIRouter(prefix="/accounts", tags=["accounts"])


def _to_out(a: GwAccount) -> AccountOut:
    return AccountOut(
        id=str(a.id),
        email=a.email,
        full_name=a.full_name,
        org_unit_path=a.org_unit_path,
        is_workspace_admin=a.is_workspace_admin,
        workspace_status=a.workspace_status,
        is_backup_enabled=a.is_backup_enabled,
        backup_enabled_at=a.backup_enabled_at,
        imap_enabled=a.imap_enabled,
        drive_vault_folder_id=a.drive_vault_folder_id,
        last_sync_at=a.last_sync_at,
        last_successful_backup_at=a.last_successful_backup_at,
        total_bytes_cache=a.total_bytes_cache,
        total_messages_cache=a.total_messages_cache,
    )


@router.get("", response_model=list[AccountOut])
async def list_accounts(
    enabled: bool | None = None,
    db: AsyncSession = Depends(get_db),
    _u: SysUser = Depends(require_permission("accounts.view")),
) -> list[AccountOut]:
    stmt = select(GwAccount).order_by(GwAccount.email.asc())
    if enabled is not None:
        stmt = stmt.where(GwAccount.is_backup_enabled.is_(enabled))
    rows = (await db.execute(stmt)).scalars().all()
    return [_to_out(a) for a in rows]


@router.post("/sync", response_model=SyncOut)
async def sync_now(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("accounts.sync")),
) -> SyncOut:
    stats = await sync_workspace_directory(db, triggered_by_user_id=str(current.id))
    await record_audit(
        db,
        action=AuditAction.SETTING_CHANGED,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        target_table="gw_accounts",
        message="directory_sync",
        metadata=stats,
    )
    await db.commit()
    return SyncOut(**stats)


async def _load(db: AsyncSession, account_id: uuid.UUID) -> GwAccount:
    stmt = select(GwAccount).where(GwAccount.id == account_id)
    acc = (await db.execute(stmt)).scalar_one_or_none()
    if acc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account_not_found")
    return acc


@router.post("/{account_id}/approve", response_model=AccountOut)
async def approve(
    account_id: uuid.UUID,
    _payload: AccountApproveIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("accounts.approve")),
) -> AccountOut:
    acc = await _load(db, account_id)
    try:
        await approve_account(db, acc, approved_by_user_id=str(current.id))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    await record_audit(
        db,
        action=AuditAction.ACCOUNT_APPROVED,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        target_table="gw_accounts",
        target_id=str(acc.id),
        metadata={"email": acc.email},
    )
    await db.commit()
    await db.refresh(acc)
    return _to_out(acc)


@router.post(
    "/{account_id}/provision-mailbox",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def provision_mailbox(
    account_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("accounts.approve")),
) -> None:
    """Crea Maildir (cur/new/tmp) en el volumen compartido con Dovecot."""
    from app.services.maildir_paths import maildir_home_from_email, maildir_root_for_account
    from app.services.maildir_service import ensure_maildir_layout

    acc = await _load(db, account_id)
    if not acc.is_backup_enabled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "backup_not_enabled")
    if not (acc.maildir_path or "").strip():
        acc.maildir_path = maildir_home_from_email(acc.email)
    ensure_maildir_layout(maildir_root_for_account(acc))
    await record_audit(
        db,
        action=AuditAction.SETTING_CHANGED,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        target_table="gw_accounts",
        target_id=str(acc.id),
        message="maildir_provisioned",
    )
    await db.commit()


@router.post("/{account_id}/revoke", response_model=AccountOut)
async def revoke(
    account_id: uuid.UUID,
    payload: AccountRevokeIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("accounts.revoke")),
) -> AccountOut:
    acc = await _load(db, account_id)
    await revoke_account(db, acc)
    await record_audit(
        db,
        action=AuditAction.ACCOUNT_REVOKED,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        target_table="gw_accounts",
        target_id=str(acc.id),
        metadata={"email": acc.email, "reason": payload.reason},
    )
    await db.commit()
    await db.refresh(acc)
    return _to_out(acc)
