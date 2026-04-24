"""Celery task: Gmail backup + Maildir conversion for one account."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.backup_engine import run_gmail_backup
from app.services.backup_job_context import load_task_account_for_backup
from app.workers.celery_app import celery_app
from app.workers.session import run_async, with_session


async def _execute(
    task_id: str, account_id: str, celery_task_id: str, run_batch_id: str | None
) -> dict[str, Any]:
    async def inner(db: AsyncSession) -> dict[str, Any]:
        pair = await load_task_account_for_backup(
            db,
            task_id=uuid.UUID(task_id),
            account_id=uuid.UUID(account_id),
        )
        if pair is None:
            return {"ok": False, "error": "task_account_not_eligible"}
        task, account = pair
        batch_uuid = None
        if run_batch_id:
            try:
                batch_uuid = uuid.UUID(run_batch_id)
            except ValueError:
                return {"ok": False, "error": "invalid_batch_id"}
        log = await run_gmail_backup(
            db,
            task=task,
            account=account,
            celery_task_id=celery_task_id,
            run_batch_id=batch_uuid,
        )
        return {"ok": True, "log_id": str(log.id), "status": log.status}

    return await with_session(inner)


@celery_app.task(bind=True, name="app.workers.tasks.backup_gmail.run")
def run(self, task_id: str, account_id: str, run_batch_id: str | None = None) -> dict[str, Any]:
    return run_async(_execute(task_id, account_id, self.request.id, run_batch_id))
