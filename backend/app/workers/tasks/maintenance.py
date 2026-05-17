"""Scheduled maintenance tasks: platform backup, directory sync, cleanup."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tasks import BackupTask
from app.models.users import SysSession
from app.services.accounts_service import sync_workspace_directory
from app.workers.celery_app import celery_app
from app.workers.session import run_async, with_session


@celery_app.task(name="app.workers.tasks.maintenance.platform_backup_daily")
def platform_backup_daily() -> dict[str, Any]:
    from app.services.platform_backup import run_platform_backup

    async def inner(db: AsyncSession) -> dict[str, Any]:
        return await run_platform_backup(db)

    return run_async(with_session(inner))


@celery_app.task(name="app.workers.tasks.maintenance.sync_directory")
def sync_directory() -> dict[str, Any]:
    async def inner(db: AsyncSession) -> dict[str, Any]:
        try:
            return await sync_workspace_directory(db)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    return run_async(with_session(inner))


@celery_app.task(name="app.workers.tasks.maintenance.cleanup_expired_sessions")
def cleanup_expired_sessions() -> dict[str, Any]:
    async def inner(db: AsyncSession) -> dict[str, Any]:
        cutoff = datetime.now(UTC) - timedelta(days=30)
        stmt = delete(SysSession).where(
            (SysSession.expires_at < datetime.now(UTC))
            | (SysSession.revoked_at < cutoff)
        )
        result = await db.execute(stmt)
        from app.services.gmail_vault_materialize_service import (
            cleanup_all_expired_materializations,
        )

        mat_purged = await cleanup_all_expired_materializations(db)
        return {"deleted": result.rowcount or 0, "gmail_vault_materializations_purged": mat_purged}

    return run_async(with_session(inner))


@celery_app.task(name="app.workers.tasks.maintenance.host_docker_prune_scheduled_tick")
def host_docker_prune_scheduled_tick() -> dict[str, Any]:
    from app.services.host_ops_service import maybe_run_scheduled_docker_prune

    async def inner(db: AsyncSession) -> dict[str, Any]:
        return await maybe_run_scheduled_docker_prune(db)

    return run_async(with_session(inner))


@celery_app.task(name="app.workers.tasks.maintenance.dispatch_scheduled_backups")
def dispatch_scheduled_backups() -> dict[str, Any]:
    """Scan enabled backup_tasks that match the current minute and queue them."""
    from app.workers.tasks.backup_drive import run as run_drive
    from app.workers.tasks.backup_gmail import run as run_gmail

    async def inner(db: AsyncSession) -> dict[str, Any]:
        from sqlalchemy.orm import selectinload

        now = datetime.now(UTC)
        stmt = (
            select(BackupTask)
            .options(selectinload(BackupTask.accounts))
            .where(BackupTask.is_enabled.is_(True))
        )
        from app.models.enums import BackupScope, BackupStatus
        from app.services.backup_concurrency_service import (
            active_backup_log_id,
            any_active_backup_for_task_definition,
            drive_scope_stored_in_log,
        )

        tasks = (await db.execute(stmt)).scalars().all()
        queued = 0
        skipped_active = 0
        skipped_task_busy = 0
        from app.services.backup_batch_registry import init_gmail_wave_queue, store_batch_celery_ids

        for task in tasks:
            if task.schedule_kind != "daily":
                continue
            if task.run_at_hour != now.hour or (task.run_at_minute or 0) != now.minute:
                continue
            if await any_active_backup_for_task_definition(
                db, task_id=task.id, task_scope=task.scope
            ):
                skipped_task_busy += 1
                continue
            accounts = (
                [a for a in task.accounts if a.is_backup_enabled]
                if task.accounts
                else []
            )
            batch_id = uuid.uuid4()
            batch_str = str(batch_id)
            celery_ids: list[str] = []
            parallel = max(1, int(task.max_parallel_accounts or 2))

            gmail_eligible_ids: list[uuid.UUID] = []
            for account in accounts:
                if task.scope not in ("gmail", "full"):
                    continue
                if await active_backup_log_id(
                    db,
                    task_id=task.id,
                    account_id=account.id,
                    log_scope=BackupScope.GMAIL.value,
                ):
                    skipped_active += 1
                    continue
                gmail_eligible_ids.append(account.id)

            pending_gmail = [str(aid) for aid in gmail_eligible_ids[parallel:]]
            await init_gmail_wave_queue(batch_str, pending_gmail)
            gmail_queued = set(pending_gmail)
            gmail_eligible_set = set(gmail_eligible_ids)

            for account in accounts:
                if task.scope in ("drive_root", "drive_computadoras", "full"):
                    if await active_backup_log_id(
                        db,
                        task_id=task.id,
                        account_id=account.id,
                        log_scope=drive_scope_stored_in_log(task.scope),
                    ):
                        skipped_active += 1
                        continue
                    r = run_drive.delay(str(task.id), str(account.id), batch_str)
                    celery_ids.append(r.id)
                    queued += 1
                if task.scope in ("gmail", "full"):
                    if account.id not in gmail_eligible_set:
                        continue
                    if str(account.id) in gmail_queued:
                        continue
                    r = run_gmail.delay(str(task.id), str(account.id), batch_str)
                    celery_ids.append(r.id)
                    queued += 1
            if celery_ids:
                await store_batch_celery_ids(batch_str, celery_ids)
                task.last_run_at = datetime.now(UTC)
                task.last_status = BackupStatus.RUNNING.value
        return {
            "dispatched": queued,
            "skipped_active": skipped_active,
            "skipped_task_busy": skipped_task_busy,
        }

    return run_async(with_session(inner))


@celery_app.task(
    bind=True,
    name="app.workers.tasks.maintenance.vault_shared_drive_item_count",
    soft_time_limit=60 * 55,
    time_limit=60 * 58,
)
def vault_shared_drive_item_count(self) -> dict[str, Any]:
    """Cuenta ítems en la Shared Drive vault (Drive API paginada; puede tardar >10 min)."""
    from app.services.host_ops_service import compute_vault_shared_drive_item_count
    from app.services.vault_shared_drive_item_count_status import (
        vault_item_count_publish_failure,
        vault_item_count_publish_running,
        vault_item_count_publish_success,
    )

    tid = str(self.request.id)

    async def inner(db: AsyncSession) -> dict[str, Any]:
        await vault_item_count_publish_running(tid)
        try:
            out = await compute_vault_shared_drive_item_count(db, publish_page_progress=True)
            data = out.model_dump()
            await vault_item_count_publish_success(tid, data)
            return data
        except Exception as exc:  # noqa: BLE001
            await vault_item_count_publish_failure(tid, str(exc))
            raise

    return run_async(with_session(inner))


@celery_app.task(name="app.workers.tasks.maintenance.cleanup_gyb_zip_tmp")
def cleanup_gyb_zip_tmp() -> dict[str, Any]:
    """Ejecutar en worker: borra ``/tmp/msa_gyb_zip_*`` en ese contenedor."""
    from app.services.host_ops_service import cleanup_gyb_zip_staging_tmp

    return cleanup_gyb_zip_staging_tmp()
