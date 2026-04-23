"""Scheduled maintenance tasks: platform backup, directory sync, cleanup."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        stmt = delete(SysSession).where(
            (SysSession.expires_at < datetime.now(timezone.utc))
            | (SysSession.revoked_at < cutoff)
        )
        result = await db.execute(stmt)
        return {"deleted": result.rowcount or 0}

    return run_async(with_session(inner))


@celery_app.task(name="app.workers.tasks.maintenance.dispatch_scheduled_backups")
def dispatch_scheduled_backups() -> dict[str, Any]:
    """Scan enabled backup_tasks that match the current minute and queue them."""
    from app.workers.tasks.backup_drive import run as run_drive
    from app.workers.tasks.backup_gmail import run as run_gmail

    async def inner(db: AsyncSession) -> dict[str, Any]:
        from sqlalchemy.orm import selectinload

        now = datetime.now(timezone.utc)
        stmt = (
            select(BackupTask)
            .options(selectinload(BackupTask.accounts))
            .where(BackupTask.is_enabled.is_(True))
        )
        tasks = (await db.execute(stmt)).scalars().all()
        queued = 0
        for task in tasks:
            if task.schedule_kind != "daily":
                continue
            if task.run_at_hour != now.hour or (task.run_at_minute or 0) != now.minute:
                continue
            accounts = (
                [a for a in task.accounts if a.is_backup_enabled]
                if task.accounts
                else []
            )
            for account in accounts:
                if task.scope in ("drive_root", "drive_computadoras", "full"):
                    run_drive.delay(str(task.id), str(account.id))
                    queued += 1
                if task.scope in ("gmail", "full"):
                    run_gmail.delay(str(task.id), str(account.id))
                    queued += 1
        return {"dispatched": queued}

    return run_async(with_session(inner))
