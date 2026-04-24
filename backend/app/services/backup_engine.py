"""High-level backup orchestration used by Celery tasks.

Provides a single entry point per scope (Drive / Gmail) that:
  * Loads the ``BackupTask`` + ``GwAccount``.
  * Creates a ``BackupLog`` in RUNNING state.
  * Streams progress to Redis so the UI WebSocket sees live updates.
  * Runs rclone / gyb / maildir conversion inside a controlled temp dir.
  * Writes a SHA-256 manifest and updates totals in the account row.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import uuid
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accounts import GwAccount
from app.models.enums import BackupScope, BackupStatus
from app.models.tasks import BackupLog, BackupTask
from app.services import drive_retention, gyb_service, maildir_service, rclone_service
from app.services.backup_batch_registry import is_batch_cancelled, set_log_cancelled
from app.services.maildir_paths import maildir_home_from_email, maildir_root_for_account
from app.services.progress_bus import publish
from app.services.settings_service import (
    KEY_VAULT_ROOT_FOLDER_ID,
    KEY_VAULT_SHARED_DRIVE_ID,
    get_value,
)


async def _create_log(
    db: AsyncSession,
    *,
    task: BackupTask,
    account: GwAccount,
    scope: BackupScope,
    celery_task_id: str | None,
    run_batch_id: uuid.UUID | None = None,
) -> BackupLog:
    log = BackupLog(
        task_id=task.id,
        account_id=account.id,
        run_batch_id=run_batch_id,
        status=BackupStatus.RUNNING.value,
        scope=scope.value,
        mode=task.mode,
        started_at=datetime.now(timezone.utc),
        pid=os.getpid(),
        celery_task_id=celery_task_id,
    )
    db.add(log)
    await db.flush()
    return log


async def _finalise_log(
    db: AsyncSession,
    log: BackupLog,
    *,
    status: BackupStatus,
    error_summary: str | None = None,
    stats: dict[str, Any] | None = None,
) -> None:
    log.status = status.value
    log.finished_at = datetime.now(timezone.utc)
    if error_summary:
        log.error_summary = error_summary[:10000]
    if stats:
        log.bytes_transferred = int(stats.get("bytes", 0)) or log.bytes_transferred
        log.files_count = int(stats.get("files", 0)) or log.files_count
        log.messages_count = int(stats.get("messages", 0)) or log.messages_count
        log.errors_count = int(stats.get("errors", 0)) or log.errors_count
    await db.flush()


def _write_manifest(root: Path, manifest_path: Path) -> tuple[int, int]:
    """Produce a SHA-256 manifest of every regular file under `root`."""
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    total_bytes = 0
    files = 0
    with manifest_path.open("w", encoding="utf-8") as out:
        for entry in sorted(root.rglob("*")):
            if not entry.is_file():
                continue
            h = hashlib.sha256()
            size = 0
            with entry.open("rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
                    size += len(chunk)
            rel = entry.relative_to(root).as_posix()
            out.write(f"{h.hexdigest()}  {size}  {rel}\n")
            total_bytes += size
            files += 1
    return files, total_bytes


async def run_drive_backup(
    db: AsyncSession,
    *,
    task: BackupTask,
    account: GwAccount,
    celery_task_id: str | None = None,
    run_batch_id: uuid.UUID | None = None,
) -> BackupLog:
    log = await _create_log(
        db,
        task=task,
        account=account,
        scope=BackupScope.DRIVE_ROOT,
        celery_task_id=celery_task_id,
        run_batch_id=run_batch_id,
    )
    await db.commit()

    log_id = str(log.id)
    await publish(log_id, {"stage": "start", "scope": "drive", "account": account.email})

    if run_batch_id and await is_batch_cancelled(str(run_batch_id)):
        await _finalise_log(db, log, status=BackupStatus.CANCELLED, error_summary="batch_aborted")
        await publish(log_id, {"stage": "cancelled", "reason": "batch"})
        await db.commit()
        return log

    vault = account.drive_vault_folder_id
    if not vault:
        await _finalise_log(db, log, status=BackupStatus.FAILED, error_summary="missing_vault_folder")
        await db.commit()
        return log

    if not (account.maildir_path or "").strip():
        account.maildir_path = maildir_home_from_email(account.email)
    maildir_root = maildir_root_for_account(account)
    await asyncio.to_thread(maildir_service.ensure_maildir_layout, maildir_root)

    try:
        async with rclone_service.build_rclone_config(
            db, impersonate_email=account.email, vault_folder_id=vault
        ) as cfg:
            drive_subpath = "Computadoras/" if task.scope == BackupScope.DRIVE_COMPUTADORAS.value else ""
            mode = "sync" if task.mode == "mirror" else "copy"
            from app.core.config import get_settings

            bwlimit = get_settings().rclone_bwlimit or None

            filters = task.filters_json or {}
            dest_subpath: str | None = None
            if filters.get("drive_layout") == "dated_run":
                stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M")
                prefix = str(filters.get("dated_run_prefix", "MSA_Runs")).strip("/") or "MSA_Runs"
                dest_subpath = f"{prefix}/{stamp}"
            # dated_run: copia bajo vault/MSA_Runs/<stamp>/ (árbol completo de la ejecución).
            # Delta real archivo-a-archivo vs corrida anterior: pendiente (--compare-dest).

            argv = rclone_service.build_rclone_argv(
                cfg,
                mode=mode,
                subpath=drive_subpath,
                dest_subpath=dest_subpath,
                bwlimit=bwlimit,
                dry_run=task.dry_run,
            )

            def _on_line(line: str) -> None:
                asyncio.run_coroutine_threadsafe(
                    publish(log_id, {"stage": "progress", "raw": line}),
                    asyncio.get_event_loop(),
                )

            rc, output = await rclone_service.run_rclone(
                argv, on_line=lambda l: None, cancel_log_id=log_id
            )
            await db.refresh(log)
            if log.status == BackupStatus.CANCELLED.value:
                await publish(log_id, {"stage": "cancelled"})
                await db.commit()
                return log
            if rc != 0:
                await _finalise_log(
                    db,
                    log,
                    status=BackupStatus.FAILED,
                    error_summary=f"rclone_rc={rc}\n{output[-4000:]}",
                )
                await publish(log_id, {"stage": "failed", "returncode": rc})
                await db.commit()
                return log
    except Exception as exc:  # pragma: no cover
        await _finalise_log(db, log, status=BackupStatus.FAILED, error_summary=str(exc))
        await publish(log_id, {"stage": "failed", "error": str(exc)})
        await db.commit()
        return log

    status = BackupStatus.SUCCESS
    await _finalise_log(db, log, status=status)
    account.last_successful_backup_at = datetime.now(timezone.utc)
    if not task.dry_run:
        try:
            removed = await drive_retention.prune_after_drive_backup(db, task=task, account=account)
            if removed:
                await publish(log_id, {"stage": "retention", "deleted_snapshots": removed})
        except Exception as exc:  # pragma: no cover
            await publish(log_id, {"stage": "retention_warning", "error": str(exc)})
    await publish(log_id, {"stage": "done", "status": status.value})
    await db.commit()
    return log


async def run_gmail_backup(
    db: AsyncSession,
    *,
    task: BackupTask,
    account: GwAccount,
    celery_task_id: str | None = None,
    run_batch_id: uuid.UUID | None = None,
) -> BackupLog:
    log = await _create_log(
        db,
        task=task,
        account=account,
        scope=BackupScope.GMAIL,
        celery_task_id=celery_task_id,
        run_batch_id=run_batch_id,
    )
    await db.commit()
    log_id = str(log.id)
    await publish(log_id, {"stage": "start", "scope": "gmail", "account": account.email})

    if run_batch_id and await is_batch_cancelled(str(run_batch_id)):
        await _finalise_log(db, log, status=BackupStatus.CANCELLED, error_summary="batch_aborted")
        await publish(log_id, {"stage": "cancelled", "reason": "batch"})
        await db.commit()
        return log

    work_root = Path(f"/var/msa/work/gmail/{account.email}")
    work_root.mkdir(parents=True, exist_ok=True)
    if not (account.maildir_path or "").strip():
        account.maildir_path = maildir_home_from_email(account.email)
    maildir_target = maildir_root_for_account(account)
    await asyncio.to_thread(maildir_service.ensure_maildir_layout, maildir_target)
    manifest_path = work_root / "manifest.sha256"

    try:
        async with gyb_service.prepare_gyb_workspace(
            db, account_email=account.email, local_folder=str(work_root)
        ) as workspace:
            argv = gyb_service.build_gyb_argv(workspace, email=account.email, action="backup")
            rc, output = await gyb_service.run_gyb(argv, cancel_log_id=log_id)
            await db.refresh(log)
            if log.status == BackupStatus.CANCELLED.value:
                await publish(log_id, {"stage": "cancelled"})
                await db.commit()
                return log
            if rc != 0:
                await _finalise_log(
                    db,
                    log,
                    status=BackupStatus.FAILED,
                    error_summary=f"gyb_rc={rc}\n{output[-4000:]}",
                )
                await publish(log_id, {"stage": "failed", "returncode": rc})
                await db.commit()
                return log

        if not task.dry_run:
            stats = await asyncio.to_thread(
                maildir_service.import_mbox_tree_to_maildir,
                mbox_root=work_root,
                maildir_root=maildir_target,
            )
        else:
            stats = maildir_service.MaildirImportStats()

        await db.refresh(log)
        if log.status == BackupStatus.CANCELLED.value:
            await publish(log_id, {"stage": "cancelled"})
            await db.commit()
            return log

        files, total_bytes = await asyncio.to_thread(_write_manifest, maildir_target, manifest_path)
    except Exception as exc:  # pragma: no cover
        await _finalise_log(db, log, status=BackupStatus.FAILED, error_summary=str(exc))
        await publish(log_id, {"stage": "failed", "error": str(exc)})
        await db.commit()
        return log

    await _finalise_log(
        db,
        log,
        status=BackupStatus.SUCCESS,
        stats={
            "messages": stats.messages,
            "files": files,
            "bytes": total_bytes,
        },
    )
    log.sha256_manifest_path = str(manifest_path)
    log.destination_path = str(maildir_target)
    account.imap_enabled = True
    account.total_messages_cache = stats.messages
    account.total_bytes_cache = total_bytes
    account.last_successful_backup_at = datetime.now(timezone.utc)
    if not task.dry_run:
        account.maildir_user_cleared_at = None
    await publish(log_id, {"stage": "done", "status": "success", "messages": stats.messages})
    await db.commit()
    return log


async def cancel_backup(db: AsyncSession, log_id: uuid.UUID) -> bool:
    stmt = select(BackupLog).where(BackupLog.id == log_id)
    log = (await db.execute(stmt)).scalar_one_or_none()
    if log is None:
        return False
    if log.status not in {BackupStatus.RUNNING.value, BackupStatus.PENDING.value, BackupStatus.QUEUED.value}:
        return False
    await set_log_cancelled(str(log.id))
    log.status = BackupStatus.CANCELLED.value
    log.finished_at = datetime.now(timezone.utc)
    await db.commit()
    await publish(str(log.id), {"stage": "cancelled"})
    return True
