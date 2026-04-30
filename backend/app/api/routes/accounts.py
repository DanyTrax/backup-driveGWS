"""Google Workspace account listing, opt-in and sync."""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_client_ip,
    get_db,
    get_user_agent,
    get_user_permissions,
    require_any_permission,
    require_permission,
)
from app.core.database import AsyncSessionLocal
from app.models.accounts import GwAccount
from app.models.enums import AuditAction, BackupScope, BackupStatus
from app.models.mailbox_delegation import SysUserMailboxDelegation
from app.models.tasks import BackupLog
from app.models.users import SysUser
from app.schemas.accounts import (
    AccountAccessCheckOut,
    AccountApproveIn,
    AccountOut,
    AccountRevokeIn,
    SyncOut,
    VerifyAccessStreamStartOut,
)
from app.schemas.mail_purge import (
    AccountMailPurgeIn,
    AccountMailPurgeOut,
    MailDataInventoryOut,
    MaildirRebuildFromGybOut,
)
from app.services.account_access_service import verify_account_access
from app.services.accounts_service import (
    approve_account,
    revoke_account,
    sync_workspace_directory,
)
from app.services.audit_service import record_audit
from app.services.mail_purge_service import (
    AccountMailPurgeOptions,
    build_mail_inventory,
    gyb_work_root_for_email,
    purge_account_mail_local,
)
from app.services.maildir_paths import maildir_home_from_email, maildir_root_for_account
from app.services.maildir_service import rebuild_maildir_from_local_gyb_workdir
from app.services.panel_synthetic_task import get_or_create_panel_maildir_gyb_rebuild_task
from app.services.progress_bus import publish

router = APIRouter(prefix="/accounts", tags=["accounts"])


def _maildir_ready(root: Path) -> bool:
    return all((root / sub).is_dir() for sub in ("cur", "new", "tmp"))


def _to_out(a: GwAccount) -> AccountOut:
    mroot = maildir_root_for_account(a)
    on_disk = _maildir_ready(mroot)
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
        maildir_on_disk=on_disk,
        maildir_user_cleared_at=a.maildir_user_cleared_at,
    )


@router.get("", response_model=list[AccountOut])
async def list_accounts(
    enabled: bool | None = None,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("accounts.view")),
) -> list[AccountOut]:
    stmt = select(GwAccount).order_by(GwAccount.email.asc())
    if enabled is not None:
        stmt = stmt.where(GwAccount.is_backup_enabled.is_(enabled))
    perms = get_user_permissions(current)
    if "mailbox.view_delegated" in perms and "mailbox.view_all" not in perms:
        stmt = stmt.where(
            GwAccount.id.in_(
                select(SysUserMailboxDelegation.gw_account_id).where(
                    SysUserMailboxDelegation.sys_user_id == current.id
                )
            )
        )
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


async def _verify_access_stream_task(account_id: uuid.UUID, session_id: str) -> None:
    try:
        async with AsyncSessionLocal() as db:
            acc = (
                (await db.execute(select(GwAccount).where(GwAccount.id == account_id)))
                .scalar_one_or_none()
            )
            if acc is None:
                await publish(
                    session_id,
                    {
                        "stage": "verify_access",
                        "phase": "error",
                        "progress_pct": 0,
                        "message": "account_not_found",
                    },
                )
                return
            await verify_account_access(db, acc, progress_id=session_id)
    except Exception as exc:  # pragma: no cover
        await publish(
            session_id,
            {
                "stage": "verify_access",
                "phase": "error",
                "progress_pct": 0,
                "message": str(exc)[:4000],
            },
        )


@router.post(
    "/{account_id}/verify-access/stream",
    response_model=VerifyAccessStreamStartOut,
    summary="Iniciar comprobación con progreso en vivo (WebSocket)",
)
async def verify_access_stream_start(
    account_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _u: SysUser = Depends(require_permission("accounts.view")),
) -> VerifyAccessStreamStartOut:
    """Devuelve ``session_id``. Conectá el cliente a ``/api/backup/ws/progress/{session_id}?token=…``.

    Los eventos llevan ``stage: verify_access`` y ``phase`` / ``progress_pct`` / ``message``.
    Al terminar, ``phase: complete`` incluye ``result`` con el mismo cuerpo que GET verify-access.
    """
    await _load(db, account_id)
    session_id = str(uuid.uuid4())
    background_tasks.add_task(_verify_access_stream_task, account_id, session_id)
    return VerifyAccessStreamStartOut(session_id=session_id)


@router.get(
    "/{account_id}/verify-access",
    response_model=AccountAccessCheckOut,
    summary="Comprobar acceso Drive, Gmail y Maildir local",
)
async def verify_access(
    account_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _u: SysUser = Depends(require_permission("accounts.view")),
) -> AccountAccessCheckOut:
    """Ejecuta ``rclone about`` (delegación), ``rclone lsf`` al vault si existe, y ``gyb --action estimate``.

    No modifica datos; puede tardar decenas de segundos si el buzón es grande (estimate).
    """
    acc = await _load(db, account_id)
    data = await verify_account_access(db, acc)
    return AccountAccessCheckOut.model_validate(data)


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


@router.get(
    "/{account_id}/mail-data-inventory",
    response_model=MailDataInventoryOut,
    summary="Inventario de datos locales de correo (Maildir, GYB, logs Gmail, webmail)",
)
async def mail_data_inventory(
    account_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _u: SysUser = Depends(
        require_any_permission(
            "accounts.purge_mail_local",
            "accounts.edit",
        )
    ),
) -> MailDataInventoryOut:
    acc = await _load(db, account_id)
    data = await build_mail_inventory(db, acc)
    return MailDataInventoryOut.model_validate(data)


@router.post(
    "/{account_id}/mail-data-purge",
    response_model=AccountMailPurgeOut,
    summary="Purgar datos locales de correo de una cuenta (opciones selectivas)",
)
async def mail_data_purge(
    account_id: uuid.UUID,
    payload: AccountMailPurgeIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("accounts.purge_mail_local")),
) -> AccountMailPurgeOut:
    acc = await _load(db, account_id)
    selected = (
        payload.maildir,
        payload.gyb_workdir,
        payload.gmail_backup_logs,
        payload.webmail_tokens,
        payload.revoke_imap_credentials,
    )
    if not any(selected):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="no_purge_options_selected",
        )
    if payload.confirmation_email.strip().lower() != acc.email.strip().lower():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="confirmation_email_mismatch")

    opts = AccountMailPurgeOptions(
        maildir=payload.maildir,
        gyb_workdir=payload.gyb_workdir,
        gmail_backup_logs=payload.gmail_backup_logs,
        webmail_tokens=payload.webmail_tokens,
        revoke_imap_credentials=payload.revoke_imap_credentials,
    )
    counts = await purge_account_mail_local(db, account=acc, opts=opts)
    await record_audit(
        db,
        action=AuditAction.MAIL_DATA_PURGED,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        target_table="gw_accounts",
        target_id=str(acc.id),
        message="account_mail_data_purge",
        metadata={**dict(counts), "email": acc.email},
    )
    await db.commit()
    await db.refresh(acc)
    return AccountMailPurgeOut.model_validate(counts)


@router.post(
    "/{account_id}/maildir/rebuild-from-local-gyb",
    response_model=MaildirRebuildFromGybOut,
    summary="Reconstruir Maildir desde export GYB en disco (sin descargar Gmail)",
)
async def maildir_rebuild_from_local_gyb(
    account_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("accounts.edit")),
) -> MaildirRebuildFromGybOut:
    """Reimporta desde ``/var/msa/work/gmail/<email>/`` si existen ``msg-db.sqlite`` y ``.eml``."""

    acc = await _load(db, account_id)
    if acc.is_backup_enabled is not True and acc.imap_enabled is not True:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "backup_or_imap_required",
        )
    if not (acc.maildir_path or "").strip():
        acc.maildir_path = maildir_home_from_email(acc.email)
    work_root = gyb_work_root_for_email(acc.email)
    mroot = maildir_root_for_account(acc)

    task = await get_or_create_panel_maildir_gyb_rebuild_task(db)
    log = BackupLog(
        task_id=task.id,
        account_id=acc.id,
        status=BackupStatus.RUNNING.value,
        scope=BackupScope.GMAIL.value,
        mode=task.mode,
        started_at=datetime.now(UTC),
        finished_at=None,
        pid=os.getpid(),
        destination_path=str(mroot),
    )
    db.add(log)
    await db.flush()
    log_id_str = str(log.id)

    try:
        await publish(
            log_id_str,
            {
                "stage": "maildir_rebuild_gyb",
                "phase": "running",
                "progress_pct": 0,
                "message": "Reorganizando Maildir desde el export GYB en disco (sin Gmail)…",
                "account": acc.email,
            },
        )
        stats = await asyncio.to_thread(
            lambda: rebuild_maildir_from_local_gyb_workdir(
                work_root=work_root,
                maildir_root=mroot,
            ),
        )
    except ValueError as exc:
        code = str(exc.args[0]) if exc.args else "rebuild_precondition_failed"
        fin = datetime.now(UTC)
        log.status = BackupStatus.FAILED.value
        log.finished_at = fin
        log.error_summary = f"Reorganizar Maildir desde GYB: precondición no cumplida ({code})."
        task.last_run_at = fin
        task.last_status = BackupStatus.FAILED.value
        await publish(
            log_id_str,
            {
                "stage": "maildir_rebuild_gyb",
                "phase": "failed",
                "progress_pct": 0,
                "message": log.error_summary,
                "error_code": code,
            },
        )
        await record_audit(
            db,
            action=AuditAction.SETTING_CHANGED,
            actor_user_id=current.id,
            actor_label=current.email,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
            target_table="gw_accounts",
            target_id=str(acc.id),
            message="maildir_rebuild_from_local_gyb_failed",
            metadata={
                "email": acc.email,
                "backup_log_id": log_id_str,
                "error": code,
            },
        )
        await db.commit()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"error": code},
        ) from exc
    except OSError as exc:
        fin = datetime.now(UTC)
        log.status = BackupStatus.FAILED.value
        log.finished_at = fin
        log.error_summary = f"Maildir/volumen: {str(exc)[:9000]}"
        task.last_run_at = fin
        task.last_status = BackupStatus.FAILED.value
        await publish(
            log_id_str,
            {
                "stage": "maildir_rebuild_gyb",
                "phase": "failed",
                "message": "Error de E/S al escribir Maildir.",
            },
        )
        await record_audit(
            db,
            action=AuditAction.SETTING_CHANGED,
            actor_user_id=current.id,
            actor_label=current.email,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
            target_table="gw_accounts",
            target_id=str(acc.id),
            message="maildir_rebuild_from_local_gyb_failed",
            metadata={
                "email": acc.email,
                "backup_log_id": log_id_str,
                "error": "maildir_volume_unavailable",
            },
        )
        await db.commit()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "maildir_volume_unavailable",
                "reason": str(exc)[:500],
            },
        ) from exc

    fin = datetime.now(UTC)
    log.status = BackupStatus.SUCCESS.value
    log.finished_at = fin
    log.messages_count = stats.messages
    log.files_count = stats.eml_files
    log.errors_count = stats.skipped_duplicates
    log.error_summary = (
        f"Maildir reconstruido desde trabajo GYB local: {stats.messages} mensajes importados, "
        f"{stats.eml_files} ficheros .eml, {stats.mbox_files} .mbox, "
        f"{stats.folders} carpetas Maildir tocadas, "
        f"{stats.skipped_duplicates} duplicados omitidos. Origen: {work_root}."
    )
    task.last_run_at = fin
    task.last_status = BackupStatus.SUCCESS.value

    acc.maildir_user_cleared_at = None
    acc.total_messages_cache = stats.messages
    await publish(
        log_id_str,
        {
            "stage": "maildir_rebuild_gyb",
            "phase": "complete",
            "progress_pct": 100,
            "message": "Maildir actualizado desde GYB local.",
            "messages": stats.messages,
            "eml_files": stats.eml_files,
            "folders_touched": stats.folders,
            "skipped_duplicates": stats.skipped_duplicates,
        },
    )
    await record_audit(
        db,
        action=AuditAction.SETTING_CHANGED,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        target_table="gw_accounts",
        target_id=str(acc.id),
        message="maildir_rebuilt_from_local_gyb",
        metadata={
            "email": acc.email,
            "backup_log_id": log_id_str,
            "messages": stats.messages,
            "eml_files": stats.eml_files,
            "work_root": str(work_root),
        },
    )
    await db.commit()
    await db.refresh(acc)
    return MaildirRebuildFromGybOut(
        messages=stats.messages,
        eml_files=stats.eml_files,
        mbox_files=stats.mbox_files,
        folders_touched=stats.folders,
        skipped_duplicates=stats.skipped_duplicates,
        backup_log_id=log_id_str,
    )


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
    current: SysUser = Depends(
        require_any_permission(
            "accounts.approve",
            "webmail.sso_admin",
            "webmail.issue_magic_link",
        )
    ),
) -> None:
    """Crea Maildir (cur/new/tmp) en el volumen compartido con Dovecot."""
    from app.services.maildir_service import ensure_maildir_layout

    acc = await _load(db, account_id)
    await db.refresh(acc)
    if acc.is_backup_enabled is not True and acc.imap_enabled is not True:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "backup_or_imap_required",
        )
    if not (acc.maildir_path or "").strip():
        acc.maildir_path = maildir_home_from_email(acc.email)
    acc.maildir_user_cleared_at = None
    try:
        ensure_maildir_layout(maildir_root_for_account(acc))
    except (OSError, PermissionError) as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "maildir_volume_unavailable",
                "reason": str(exc)[:500],
            },
        ) from exc
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


@router.post(
    "/{account_id}/mailbox/clear",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def clear_mailbox(
    account_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("accounts.approve")),
) -> None:
    """Vacía Maildir en disco; la UI marca bandeja vacía hasta el próximo backup Gmail o aprovisionamiento."""
    from app.services.maildir_service import clear_maildir_tree

    acc = await _load(db, account_id)
    if not acc.imap_enabled and not acc.is_backup_enabled:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "imap_or_backup_required",
        )
    if not (acc.maildir_path or "").strip():
        acc.maildir_path = maildir_home_from_email(acc.email)
    clear_maildir_tree(maildir_root_for_account(acc))
    acc.maildir_user_cleared_at = datetime.now(UTC)
    acc.total_messages_cache = 0
    acc.total_bytes_cache = 0
    await record_audit(
        db,
        action=AuditAction.SETTING_CHANGED,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        target_table="gw_accounts",
        target_id=str(acc.id),
        message="maildir_cleared_by_admin",
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