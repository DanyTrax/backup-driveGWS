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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accounts import GwAccount
from app.models.enums import BackupScope, BackupStatus
from app.models.tasks import BackupLog, BackupTask
from app.services import drive_retention, gyb_service, maildir_service, rclone_service, vault_layout
from app.services.backup_batch_registry import is_batch_cancelled, set_log_cancelled
from app.services.backup_concurrency_service import active_backup_log_id, drive_scope_stored_in_log
from app.services.gmail_backup_progress import (
    start_gmail_progress_ticker,
    stop_gmail_progress_ticker,
)
from app.services.maildir_paths import maildir_home_from_email, maildir_root_for_account
from app.services.progress_bus import publish


def _purge_gyb_workdir_contents(work_root: Path) -> None:
    """Vacia ``/var/msa/work/gmail/<email>/`` conservando el directorio raíz (no toca Maildir)."""
    if not work_root.is_dir():
        return
    for child in work_root.iterdir():
        if child.is_file() or child.is_symlink():
            child.unlink(missing_ok=True)
        else:
            shutil.rmtree(child, ignore_errors=False)


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
        started_at=datetime.now(UTC),
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
    log.finished_at = datetime.now(UTC)
    if error_summary:
        log.error_summary = error_summary[:10000]
    if stats:
        # No usar ``or log.field``: 0 es un valor válido (buzón vacío / sin mensajes importados).
        if "bytes" in stats:
            log.bytes_transferred = int(stats["bytes"])
        if "files" in stats:
            log.files_count = int(stats["files"])
        if "messages" in stats:
            log.messages_count = int(stats["messages"])
        if "errors" in stats:
            log.errors_count = int(stats["errors"])
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
    dup = await active_backup_log_id(
        db,
        task_id=task.id,
        account_id=account.id,
        log_scope=drive_scope_stored_in_log(task.scope),
    )
    if dup is not None:
        ex = await db.get(BackupLog, dup)
        if ex is not None and ex.celery_task_id != celery_task_id:
            await publish(
                str(ex.id),
                {
                    "stage": "worker_skipped",
                    "reason": "active_backup_exists",
                    "scope": "drive",
                    "duplicate_celery_id": celery_task_id,
                },
            )
            return ex

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
            dest_subpath = vault_layout.drive_dest_subpath_for_task(filters)
            # Layout: ``2-DRIVE/_sync`` (continuo) o ``2-DRIVE/MSA_Runs/<stamp>[( TOTAL|SNAPSHOT)]``;
            # legado: ``filters_json.vault_legacy_layout`` o ``vault_separated_layout: false``.

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
                argv, on_line=lambda _ln: None, cancel_log_id=log_id
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
    account.last_successful_backup_at = datetime.now(UTC)
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
    dup = await active_backup_log_id(
        db,
        task_id=task.id,
        account_id=account.id,
        log_scope=BackupScope.GMAIL.value,
    )
    if dup is not None:
        ex = await db.get(BackupLog, dup)
        if ex is not None and ex.celery_task_id != celery_task_id:
            await publish(
                str(ex.id),
                {
                    "stage": "worker_skipped",
                    "reason": "active_backup_exists",
                    "scope": "gmail",
                    "duplicate_celery_id": celery_task_id,
                },
            )
            return ex

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

    want_vault_push = vault_layout.use_gmail_vault_push(task.filters_json or {})
    vault_id = (account.drive_vault_folder_id or "").strip()
    if want_vault_push and not vault_id:
        await _finalise_log(
            db,
            log,
            status=BackupStatus.FAILED,
            error_summary="missing_drive_vault_folder_id (requerido para subir export a 1-GMAIL/ en Drive)",
        )
        await publish(log_id, {"stage": "failed", "error": "missing_vault_for_gmail_push"})
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
        gyb_fin, gyb_tick = start_gmail_progress_ticker(
            log.id, log_id, work_root, mode="gyb"
        )
        try:
            async with gyb_service.prepare_gyb_workspace(
                db, account_email=account.email, local_folder=str(work_root)
            ) as workspace:
                argv = gyb_service.build_gyb_argv(
                    workspace, email=account.email, action="backup"
                )
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
        finally:
            await stop_gmail_progress_ticker(gyb_fin, gyb_tick)

        if not task.dry_run:
            im_fin, im_tick = start_gmail_progress_ticker(
                log.id, log_id, maildir_target, mode="import_maildir"
            )
            try:
                stats = await asyncio.to_thread(
                    maildir_service.import_mbox_tree_to_maildir,
                    mbox_root=work_root,
                    maildir_root=maildir_target,
                )
            finally:
                await stop_gmail_progress_ticker(im_fin, im_tick)
        else:
            stats = maildir_service.MaildirImportStats()

        await db.refresh(log)
        if log.status == BackupStatus.CANCELLED.value:
            await publish(log_id, {"stage": "cancelled"})
            await db.commit()
            return log

        files, total_bytes = await asyncio.to_thread(_write_manifest, maildir_target, manifest_path)

        if not task.dry_run and want_vault_push:
            subp = vault_layout.gmail_vault_rclone_subpath()
            await publish(
                log_id,
                {
                    "stage": "vault_push",
                    "scope": "gmail",
                    "subpath": subp,
                },
            )
            async with rclone_service.build_rclone_vault_dest_only_config(
                db, vault_folder_id=vault_id
            ) as push_cfg:
                pargv = rclone_service.build_rclone_local_to_vault_argv(
                    str(work_root),
                    push_cfg,
                    dest_subpath=subp,
                    dry_run=False,
                )
                vrc, vout = await rclone_service.run_rclone(pargv, cancel_log_id=log_id)
                await db.refresh(log)
                if log.status == BackupStatus.CANCELLED.value:
                    await publish(log_id, {"stage": "cancelled"})
                    await db.commit()
                    return log
                if vrc != 0:
                    await _finalise_log(
                        db,
                        log,
                        status=BackupStatus.FAILED,
                        error_summary=f"vault_rclone_to_1_gmail_rc={vrc}\n{vout[-4000:]}",
                    )
                    await publish(log_id, {"stage": "failed", "scope": "vault_push", "returncode": vrc})
                    await db.commit()
                    return log

                workdir_purged = False
                want_purge = vault_layout.gmail_purge_gyb_workdir_after_vault_verified(
                    task.filters_json or {}
                )
                if want_purge:
                    cargv = rclone_service.build_rclone_check_local_vault_argv(
                        str(work_root),
                        push_cfg,
                        dest_subpath=subp,
                    )
                    crc, cout = await rclone_service.run_rclone(cargv, cancel_log_id=log_id)
                    await db.refresh(log)
                    if log.status == BackupStatus.CANCELLED.value:
                        await publish(log_id, {"stage": "cancelled"})
                        await db.commit()
                        return log
                    if crc != 0:
                        await _finalise_log(
                            db,
                            log,
                            status=BackupStatus.FAILED,
                            error_summary=(
                                "vault_rclone_check_failed_after_copy (no se vació work GYB; "
                                f"revisar 1-GMAIL/gyb_mbox en Drive)\nrc={crc}\n{cout[-4000:]}"
                            ),
                        )
                        await publish(
                            log_id,
                            {
                                "stage": "failed",
                                "scope": "vault_check",
                                "returncode": crc,
                            },
                        )
                        await db.commit()
                        return log
                    await publish(
                        log_id,
                        {
                            "stage": "gyb_workdir_purge",
                            "scope": "gmail",
                            "path": str(work_root),
                        },
                    )
                    await asyncio.to_thread(_purge_gyb_workdir_contents, work_root)
                    workdir_purged = True

            await publish(
                log_id,
                {
                    "stage": "vault_push",
                    "ok": True,
                    "scope": "gmail",
                    "workdir_purged": workdir_purged,
                },
            )
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
    account.last_successful_backup_at = datetime.now(UTC)
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
    log.finished_at = datetime.now(UTC)
    await db.commit()
    await publish(str(log.id), {"stage": "cancelled"})
    return True
