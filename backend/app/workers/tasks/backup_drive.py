"""Celery task: Drive backup for a given task/account pair."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.accounts import GwAccount
from app.models.tasks import BackupTask
from app.services.backup_engine import run_drive_backup
from app.workers.celery_app import celery_app
from app.workers.session import run_async, with_session


async def _execute(task_id: str, account_id: str, celery_task_id: str) -> dict[str, Any]:
    async def inner(db: AsyncSession) -> dict[str, Any]:
        task = (
            await db.execute(
                select(BackupTask).where(BackupTask.id == uuid.UUID(task_id))
            )
        ).scalar_one_or_none()
        account = (
            await db.execute(
                select(GwAccount).where(GwAccount.id == uuid.UUID(account_id))
            )
        ).scalar_one_or_none()
        if task is None or account is None:
            return {"ok": False, "error": "not_found"}
        log = await run_drive_backup(
            db, task=task, account=account, celery_task_id=celery_task_id
        )
        return {"ok": True, "log_id": str(log.id), "status": log.status}

    return await with_session(inner)


@celery_app.task(bind=True, name="app.workers.tasks.backup_drive.run")
def run(self, task_id: str, account_id: str) -> dict[str, Any]:
    return run_async(_execute(task_id, account_id, self.request.id))
