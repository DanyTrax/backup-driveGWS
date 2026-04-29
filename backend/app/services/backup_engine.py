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
from app.services.backup_concurrency_service import (
    acquire_backup_start_xact_lock,
    active_backup_log_id,
    drive_scope_stored_in_log,
)
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


def gyb_workdir_has_export(work_root: Path) -> bool:
    """True si queda export GYB (.eml / .mbox) en disco (reintento vault)."""
    if not work_root.is_dir():
        return False
    for p in work_root.rglob("*"):
        if p.is_file() and p.suffix.lower() in (".eml", ".mbox"):
            return True
    return False


async def run_gmail_vault_push_phase(
    db: AsyncSession,
    *,
    log: BackupLog,
    task: BackupTask,
    account: GwAccount,
    work_root: Path,
    log_id_str: str,
    want_vault_push: bool,
    vault_id: str,
) -> tuple[bool, str | None]:
    """Sube export GYB a ``1-GMAIL/gyb_mbox``. Devuelve (False, resumen) si falla rclone/check."""
    if not want_vault_push:
        return True, None

    subp = vault_layout.gmail_vault_rclone_subpath()
    await publish(
        log_id_str,
        {
            "stage": "vault_push",
            "scope": "gmail",
            "subpath": subp,
        },
    )
    async with rclone_service.build_rclone_vault_dest_only_config(
        db, vault_folder_id=vault_id
    ) as push_cfg:
        await publish(
            log_id_str,
            {
                "stage": "vault_ensure_dest",
                "scope": "gmail",
                "subpath": subp,
            },
        )
        mk_argv = rclone_service.build_rclone_mkdir_dest_argv(
            push_cfg, dest_subpath=subp
        )
        mk_rc, mk_out = await rclone_service.run_rclone(
            mk_argv, cancel_log_id=log_id_str
        )
        await db.refresh(log)
        if log.status == BackupStatus.CANCELLED.value:
            return False, "cancelled"
        if mk_rc != 0:
            return False, f"vault_rclone_mkdir_rc={mk_rc}\n{mk_out[-4000:]}"

        pargv = rclone_service.build_rclone_local_to_vault_argv(
            str(work_root),
            push_cfg,
            dest_subpath=subp,
            dry_run=False,
        )
        vrc, vout = await rclone_service.run_rclone(pargv, cancel_log_id=log_id_str)
        await db.refresh(log)
        if log.status == BackupStatus.CANCELLED.value:
            return False, "cancelled"
        if vrc != 0:
            return False, f"vault_rclone_to_1_gmail_rc={vrc}\n{vout[-4000:]}"

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
            crc, cout = await rclone_service.run_rclone(cargv, cancel_log_id=log_id_str)
            await db.refresh(log)
            if log.status == BackupStatus.CANCELLED.value:
                return False, "cancelled"
            if crc != 0:
                return (
                    False,
                    (
                        "vault_rclone_check_failed_after_copy (no se vació work GYB; "
                        f"revisar 1-GMAIL/gyb_mbox en Drive)\nrc={crc}\n{cout[-4000:]}"
                    ),
                )
            await publish(
                log_id_str,
                {
                    "stage": "gyb_workdir_purge",
                    "scope": "gmail",
                    "path": str(work_root),
                },
            )
            await asyncio.to_thread(_purge_gyb_workdir_contents, work_root)
            workdir_purged = True

        await publish(
            log_id_str,
            {
                "stage": "vault_push",
                "ok": True,
                "scope": "gmail",
                "workdir_purged": workdir_purged,
            },
        )
    return True, None


def gmail_log_vault_retry_reason(log: BackupLog, task: BackupTask) -> str | None:
    """None si se puede reintentar solo la fase vault; código corto en caso contrario."""
    if log.scope != BackupScope.GMAIL.value:
        return "not_gmail_scope"
    if log.gmail_maildir_ready_at is None:
        return "maildir_not_ready"
    if log.gmail_vault_completed_at is not None:
        return "vault_already_done"
    if log.status not in (
        BackupStatus.FAILED.value,
        BackupStatus.CANCELLED.value,
    ):
        return "invalid_status"
    if not vault_layout.use_gmail_vault_push(task.filters_json or {}):
        return "vault_push_disabled"
    return None


async def retry_gmail_vault_push(
    db: AsyncSession,
    log_id: uuid.UUID,
    celery_task_id: str,
) -> BackupLog:
    """Reanuda solo la subida al vault para un log Gmail con Maildir ya consolidado y vault pendiente."""
    stmt = select(BackupLog).where(BackupLog.id == log_id).with_for_update()
    log = (await db.execute(stmt)).scalar_one_or_none()
    if log is None:
        raise ValueError("log_not_found")

    task = await db.get(BackupTask, log.task_id)
    account = await db.get(GwAccount, log.account_id)
    if task is None or account is None:
        raise ValueError("task_or_account_missing")

    reason = gmail_log_vault_retry_reason(log, task)
    if reason:
        raise ValueError(reason)

    work_root = Path(f"/var/msa/work/gmail/{account.email}")
    if not gyb_workdir_has_export(work_root):
        raise ValueError("gyb_workdir_empty")

    vault_id = (account.drive_vault_folder_id or "").strip()
    if not vault_id:
        raise ValueError("missing_vault_folder")

    dup = await active_backup_log_id(
        db,
        task_id=log.task_id,
        account_id=log.account_id,
        log_scope=BackupScope.GMAIL.value,
    )
    if dup is not None and dup != log.id:
        raise ValueError("active_gmail_backup_exists")

    log.status = BackupStatus.RUNNING.value
    log.finished_at = None
    log.error_summary = None
    log.celery_task_id = celery_task_id
    await db.commit()
    await db.refresh(log)

    log_id_str = str(log.id)
    await publish(
        log_id_str,
        {"stage": "vault_push_retry", "scope": "gmail", "account": account.email},
    )

    maildir_target = maildir_root_for_account(account)
    manifest_path = work_root / "manifest.sha256"

    try:
        ok, err = await run_gmail_vault_push_phase(
            db,
            log=log,
            task=task,
            account=account,
            work_root=work_root,
            log_id_str=log_id_str,
            want_vault_push=True,
            vault_id=vault_id,
        )
        await db.refresh(log)
        if log.status == BackupStatus.CANCELLED.value:
            await publish(log_id_str, {"stage": "cancelled"})
            await db.commit()
            return log
        if not ok:
            if err == "cancelled":
                await publish(log_id_str, {"stage": "cancelled"})
                await db.commit()
                return log
            await _finalise_log(db, log, status=BackupStatus.FAILED, error_summary=err)
            await publish(
                log_id_str,
                {"stage": "failed", "scope": "vault_push", "retry": True},
            )
            await db.commit()
            return log

        files, total_bytes = await asyncio.to_thread(
            _write_manifest, maildir_target, manifest_path
        )
        stats_messages = log.messages_count
        await _finalise_log(
            db,
            log,
            status=BackupStatus.SUCCESS,
            stats={
                "messages": stats_messages,
                "files": files,
                "bytes": total_bytes,
            },
        )
        log.sha256_manifest_path = str(manifest_path)
        log.destination_path = str(maildir_target)
        log.gmail_vault_completed_at = datetime.now(UTC)
        account.last_successful_backup_at = datetime.now(UTC)
        account.total_bytes_cache = total_bytes
        if stats_messages:
            account.total_messages_cache = stats_messages
        await publish(
            log_id_str,
            {
                "stage": "done",
                "status": "success",
                "messages": stats_messages,
                "vault_retry": True,
            },
        )
        await db.commit()
        return log
    except Exception as exc:  # pragma: no cover
        await _finalise_log(db, log, status=BackupStatus.FAILED, error_summary=str(exc))
        await publish(log_id_str, {"stage": "failed", "error": str(exc), "retry": True})
        await db.commit()
        return log


async def run_drive_backup(
    db: AsyncSession,
    *,
    task: BackupTask,
    account: GwAccount,
    celery_task_id: str | None = None,
    run_batch_id: uuid.UUID | None = None,
) -> BackupLog:
    await acquire_backup_start_xact_lock(
        db, task_id=task.id, account_id=account.id, namespace="drive"
    )
    dup = await active_backup_log_id(
        db,
        task_id=task.id,
        account_id=account.id,
        log_scope=drive_scope_stored_in_log(task.scope),
    )
    if dup is not None:
        ex = await db.get(BackupLog, dup)
        if ex is not None and ex.celery_task_id != celery_task_id:
            await db.rollback()
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
        if ex is not None:
            await db.rollback()
            return ex

    log = await _create_log(
        db,
        task=task,
        account=account,
        scope=BackupScope(task.scope),
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
            if drive_subpath:
                ok_dir, pre_out = await rclone_service.rclone_verify_remote_dir(
                    cfg, path_under_source="Computadoras", cancel_log_id=log_id
                )
                if not ok_dir:
                    detail = (
                        "No existe o no es accesible la carpeta «Computadoras» en el Drive de esta cuenta "
                        "(debe llamarse así en la raíz de «Mi unidad», o revisá permisos / delegación).\n"
                        f"{pre_out[-3500:]}"
                    )
                    await _finalise_log(db, log, status=BackupStatus.FAILED, error_summary=detail)
                    await publish(log_id, {"stage": "failed", "error": "computadoras_folder_missing"})
                    await db.commit()
                    return log
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
    await acquire_backup_start_xact_lock(
        db, task_id=task.id, account_id=account.id, namespace="gmail"
    )
    dup = await active_backup_log_id(
        db,
        task_id=task.id,
        account_id=account.id,
        log_scope=BackupScope.GMAIL.value,
    )
    if dup is not None:
        ex = await db.get(BackupLog, dup)
        if ex is not None and ex.celery_task_id != celery_task_id:
            await db.rollback()
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
        if ex is not None:
            await db.rollback()
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
    manifest_path = work_root / "manifest.sha256"

    try:
        # 1) Una sola descarga GYB → work_root (sin tocar Maildir todavía).
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

        await publish(
            log_id,
            {
                "stage": "gyb_done",
                "scope": "gmail",
                "account": account.email,
                "next": "maildir_import",
            },
        )

        # 2) Bandeja local (import desde work_root → Maildir); crea cur/new/tmp vía import_mbox_tree_to_maildir.
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
            await publish(
                log_id,
                {
                    "stage": "maildir_ready",
                    "scope": "gmail",
                    "account": account.email,
                    "messages": stats.messages,
                    "next": "vault_push_or_finalize",
                    "local_mail_ready": True,
                },
            )
            log.gmail_maildir_ready_at = datetime.now(UTC)
            log.messages_count = stats.messages
            account.imap_enabled = True
            account.total_messages_cache = stats.messages
            account.maildir_user_cleared_at = None
            await db.commit()
            await db.refresh(log)
            await db.refresh(account)
        else:
            stats = maildir_service.MaildirImportStats()
            await asyncio.to_thread(maildir_service.ensure_maildir_layout, maildir_target)

        await db.refresh(log)
        if log.status == BackupStatus.CANCELLED.value:
            await publish(log_id, {"stage": "cancelled"})
            await db.commit()
            return log

        files, total_bytes = await asyncio.to_thread(_write_manifest, maildir_target, manifest_path)

        if not task.dry_run:
            ok, verr = await run_gmail_vault_push_phase(
                db,
                log=log,
                task=task,
                account=account,
                work_root=work_root,
                log_id_str=log_id,
                want_vault_push=want_vault_push,
                vault_id=vault_id,
            )
            await db.refresh(log)
            if log.status == BackupStatus.CANCELLED.value:
                await publish(log_id, {"stage": "cancelled"})
                await db.commit()
                return log
            if not ok:
                if verr == "cancelled":
                    await publish(log_id, {"stage": "cancelled"})
                    await db.commit()
                    return log
                await _finalise_log(
                    db,
                    log,
                    status=BackupStatus.FAILED,
                    error_summary=verr,
                )
                await publish(
                    log_id,
                    {"stage": "failed", "scope": "vault_push"},
                )
                await db.commit()
                return log
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
    if task.dry_run:
        account.imap_enabled = True
        account.total_messages_cache = stats.messages
    account.total_bytes_cache = total_bytes
    account.last_successful_backup_at = datetime.now(UTC)
    if not task.dry_run:
        account.maildir_user_cleared_at = None
        log.gmail_vault_completed_at = datetime.now(UTC)
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
