"""ZIP vault Gmail desde export ya presente en disco (sin corrida GYB completa)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accounts import GwAccount
from app.models.enums import BackupScope, BackupStatus
from app.models.tasks import BackupLog, BackupTask
from app.services import vault_layout
from app.services.backup_concurrency_service import BACKUP_ACTIVE_STATUSES
from app.services.backup_engine import _finalise_log
from app.services.gmail_vault_plan_service import GmailZipUploadDecision
from app.services.gmail_vault_zip_layout import seal_kind_to_zip_cadence_dir
from app.services.gmail_vault_zip_service import run_gmail_zip_vault_push_phase
from app.services.mail_purge_service import gyb_work_root_for_email
from app.services.maildir_service import gyb_workdir_has_eml_or_mbox


async def account_has_active_gmail_like_backup(db: AsyncSession, account_id: uuid.UUID) -> bool:
    stmt = (
        select(BackupLog.id)
        .where(
            BackupLog.account_id == account_id,
            BackupLog.status.in_(BACKUP_ACTIVE_STATUSES),
            BackupLog.scope.in_((BackupScope.GMAIL.value, BackupScope.FULL.value)),
        )
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none() is not None


async def execute_manual_gmail_vault_zip(
    db: AsyncSession,
    *,
    log_id: uuid.UUID,
    celery_task_id: str | None,
) -> None:
    log = (
        await db.execute(select(BackupLog).where(BackupLog.id == log_id))
    ).scalar_one_or_none()
    if log is None:
        return
    if log.status != BackupStatus.RUNNING.value:
        return

    if celery_task_id:
        log.celery_task_id = celery_task_id
        await db.flush()

    task = (
        await db.execute(select(BackupTask).where(BackupTask.id == log.task_id))
    ).scalar_one()
    account = (
        await db.execute(select(GwAccount).where(GwAccount.id == log.account_id))
    ).scalar_one()

    filters = task.filters_json or {}
    if not vault_layout.use_gmail_vault_zip_upload(filters):
        await _finalise_log(
            db,
            log,
            status=BackupStatus.FAILED,
            error_summary="manual_zip_requires_zip_only_or_mixed_packaging",
        )
        task.last_run_at = datetime.now(UTC)
        task.last_status = BackupStatus.FAILED.value
        return
    if not vault_layout.use_gmail_vault_push(filters):
        await _finalise_log(
            db,
            log,
            status=BackupStatus.FAILED,
            error_summary="manual_zip_requires_gmail_vault_push_enabled",
        )
        task.last_run_at = datetime.now(UTC)
        task.last_status = BackupStatus.FAILED.value
        return

    vault_id = (account.drive_vault_folder_id or "").strip()
    if not vault_id:
        await _finalise_log(
            db,
            log,
            status=BackupStatus.FAILED,
            error_summary="missing_drive_vault_folder_id",
        )
        task.last_run_at = datetime.now(UTC)
        task.last_status = BackupStatus.FAILED.value
        return

    work_root = gyb_work_root_for_email(account.email)
    if not gyb_workdir_has_eml_or_mbox(work_root):
        await _finalise_log(
            db,
            log,
            status=BackupStatus.FAILED,
            error_summary="gyb_work_no_eml_or_mbox",
        )
        task.last_run_at = datetime.now(UTC)
        task.last_status = BackupStatus.FAILED.value
        return

    tz = ZoneInfo((task.timezone or "UTC").strip() or "UTC")
    today = datetime.now(UTC).astimezone(tz).date()
    dec = GmailZipUploadDecision(
        should_upload=True,
        period_start=today,
        period_end=today,
        seal_kind="manual",
        cadence_dir=seal_kind_to_zip_cadence_dir("manual"),
        reason="manual_panel_from_local_work",
    )
    packaging_mode = vault_layout.gmail_vault_packaging_mode(filters)

    zok, zerr = await run_gmail_zip_vault_push_phase(
        db,
        log=log,
        task=task,
        account=account,
        work_root=work_root,
        log_id_str=str(log.id),
        vault_id=vault_id,
        decision=dec,
        packaging_mode=packaging_mode,
    )
    if not zok:
        if zerr == "cancelled":
            await _finalise_log(db, log, status=BackupStatus.CANCELLED)
        else:
            await _finalise_log(
                db,
                log,
                status=BackupStatus.FAILED,
                error_summary=zerr or "vault_zip_failed",
            )
        task.last_run_at = datetime.now(UTC)
        task.last_status = (
            BackupStatus.CANCELLED.value if zerr == "cancelled" else BackupStatus.FAILED.value
        )
        return

    fin = datetime.now(UTC)
    log.gmail_vault_completed_at = fin
    await _finalise_log(db, log, status=BackupStatus.SUCCESS)
    task.last_run_at = fin
    task.last_status = BackupStatus.SUCCESS.value
