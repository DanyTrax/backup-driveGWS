"""Traer export GYB desde la bóveda Drive (1-GMAIL/gyb_mbox) al disco de trabajo local."""
from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accounts import GwAccount
from app.models.enums import AuditAction, BackupStatus
from app.models.tasks import BackupLog, BackupTask
from app.services import rclone_service
from app.services.audit_service import record_audit
from app.services.backup_engine import _rclone_line_progress_pct
from app.services.mail_purge_service import _purge_gyb_workdir_contents, gyb_work_root_for_email
from app.services.progress_bus import publish
from app.services.vault_layout import gmail_vault_rclone_subpath


async def restore_gyb_workdir_from_vault(
    db: AsyncSession,
    *,
    account: GwAccount,
    purge_workdir_first: bool = False,
    progress_log_id: str | None = None,
    cancel_log_id: str | None = None,
) -> tuple[int, str, Path]:
    """``rclone copy`` vault → ``/var/msa/work/gmail/<email>/``.

    Con ``purge_workdir_first`` se vacía antes la carpeta local. Publica eventos de progreso en
    ``progress_log_id`` (misma forma que ``vault_copy``) cuando está definido.
    """
    vault_id = (account.drive_vault_folder_id or "").strip()
    if not vault_id:
        raise ValueError("missing_drive_vault_folder_id")
    work_root = gyb_work_root_for_email(account.email)
    subpath = gmail_vault_rclone_subpath()
    cid = cancel_log_id or progress_log_id

    if progress_log_id:
        await publish(
            progress_log_id,
            {
                "stage": "vault_pull_start",
                "scope": "gmail",
                "subpath": subpath,
                "message": "Iniciando copia desde la bóveda (1-GMAIL/gyb_mbox) hacia el servidor…",
                "account": account.email,
            },
        )

    if purge_workdir_first:
        if progress_log_id:
            await publish(
                progress_log_id,
                {
                    "stage": "vault_pull_purge",
                    "scope": "gmail",
                    "subpath": subpath,
                    "progress_pct": 0,
                    "message": "Vaciando carpeta de trabajo GYB local antes de restaurar desde Drive…",
                    "account": account.email,
                },
            )
        await asyncio.to_thread(_purge_gyb_workdir_contents, work_root)

    work_root.mkdir(parents=True, exist_ok=True)

    async def _emit_vault_pull(line: str, phase: str) -> None:
        s = line.strip()
        if not s:
            return
        try:
            payload: dict[str, Any] = {
                "stage": "progress",
                "scope": "gmail",
                "phase": phase,
                "raw": s,
                "rclone_mode": "copy",
            }
            pct = _rclone_line_progress_pct(s)
            if pct is not None:
                payload["progress_pct"] = round(pct, 2)
            if progress_log_id:
                await publish(progress_log_id, payload)
        except Exception:
            pass

    def _on_line_factory(phase: str):
        def _on_line(line: str) -> None:
            if not line.strip() or not progress_log_id:
                return
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return
            loop.create_task(_emit_vault_pull(line, phase))

        return _on_line

    async with rclone_service.build_rclone_vault_dest_only_config(
        db, vault_folder_id=vault_id
    ) as cfg:
        argv = rclone_service.build_rclone_vault_to_local_argv(
            str(work_root),
            cfg,
            source_subpath=subpath,
        )
        rc, out = await rclone_service.run_rclone(
            argv,
            on_line=_on_line_factory("vault_pull"),
            timeout=None,
            cancel_log_id=cid,
        )

    return rc, out, work_root


async def finalize_gyb_vault_restore_backup_log(
    db: AsyncSession,
    *,
    log_id: uuid.UUID,
    account_id: uuid.UUID,
    purge_workdir_first: bool,
    actor_user_id: uuid.UUID,
    actor_label: str,
    ip_address: str | None,
    user_agent: str | None,
) -> None:
    """Carga log/cuenta/tarea, ejecuta restauración, actualiza estado y audita."""

    log = (await db.execute(select(BackupLog).where(BackupLog.id == log_id))).scalar_one_or_none()
    account = (await db.execute(select(GwAccount).where(GwAccount.id == account_id))).scalar_one_or_none()
    if log is None or account is None:
        return
    task = (await db.execute(select(BackupTask).where(BackupTask.id == log.task_id))).scalar_one()
    log_id_str = str(log.id)

    try:
        rc, out, work_root = await restore_gyb_workdir_from_vault(
            db,
            account=account,
            purge_workdir_first=purge_workdir_first,
            progress_log_id=log_id_str,
            cancel_log_id=log_id_str,
        )
    except Exception as exc:  # noqa: BLE001
        fin = datetime.now(UTC)
        log.status = BackupStatus.FAILED.value
        log.finished_at = fin
        log.error_summary = f"Restaurar GYB desde vault: error inesperado: {str(exc)[:9000]}"
        task.last_run_at = fin
        task.last_status = BackupStatus.FAILED.value
        await publish(
            log_id_str,
            {
                "stage": "failed",
                "scope": "gmail",
                "message": log.error_summary[:600],
            },
        )
        await record_audit(
            db,
            action=AuditAction.GYB_WORK_RESTORED_FROM_VAULT,
            actor_user_id=actor_user_id,
            actor_label=actor_label,
            ip_address=ip_address,
            user_agent=user_agent,
            target_table="gw_accounts",
            target_id=str(account.id),
            success=False,
            message="gyb_restore_from_vault_failed",
            metadata={
                "email": account.email,
                "backup_log_id": log_id_str,
                "error": str(exc)[:2000],
            },
        )
        await db.commit()
        return

    tail = (out or "")[-4000:] if out else None
    fin = datetime.now(UTC)

    if rc != 0:
        log.status = BackupStatus.FAILED.value
        log.finished_at = fin
        log.error_summary = f"rclone copy desde vault falló (rc={rc}).\n{tail or ''}"
        log.destination_path = str(work_root)
        task.last_run_at = fin
        task.last_status = BackupStatus.FAILED.value
        await publish(
            log_id_str,
            {
                "stage": "failed",
                "scope": "gmail",
                "message": (log.error_summary or "")[:800],
                "rclone_exit_code": rc,
                "log_tail": tail,
            },
        )
        await record_audit(
            db,
            action=AuditAction.GYB_WORK_RESTORED_FROM_VAULT,
            actor_user_id=actor_user_id,
            actor_label=actor_label,
            ip_address=ip_address,
            user_agent=user_agent,
            target_table="gw_accounts",
            target_id=str(account.id),
            success=False,
            message="gyb_restore_from_vault_rclone_failed",
            metadata={
                "email": account.email,
                "backup_log_id": log_id_str,
                "work_path": str(work_root),
                "rclone_exit_code": rc,
                "purge_workdir_first": purge_workdir_first,
                "log_tail": tail,
            },
        )
        await db.commit()
        return

    log.status = BackupStatus.SUCCESS.value
    log.finished_at = fin
    log.destination_path = str(work_root)
    purge_note = "Se vació la carpeta local antes de copiar. " if purge_workdir_first else "Copia incremental. "
    log.error_summary = (
        f"Restauración GYB desde bóveda 1-GMAIL/gyb_mbox → {work_root}. {purge_note}rclone rc=0."
    )
    task.last_run_at = fin
    task.last_status = BackupStatus.SUCCESS.value

    await publish(
        log_id_str,
        {
            "stage": "vault_pull_done",
            "scope": "gmail",
            "progress_pct": 100,
            "message": log.error_summary[:500],
            "work_path": str(work_root),
            "purged_workdir_first": purge_workdir_first,
            "subpath": gmail_vault_rclone_subpath(),
        },
    )
    await record_audit(
        db,
        action=AuditAction.GYB_WORK_RESTORED_FROM_VAULT,
        actor_user_id=actor_user_id,
        actor_label=actor_label,
        ip_address=ip_address,
        user_agent=user_agent,
        target_table="gw_accounts",
        target_id=str(account.id),
        message="gyb_restored_from_vault",
        metadata={
            "email": account.email,
            "backup_log_id": log_id_str,
            "work_path": str(work_root),
            "rclone_exit_code": rc,
            "purge_workdir_first": purge_workdir_first,
        },
    )
    await db.commit()
