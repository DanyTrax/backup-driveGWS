"""Celery task: Gmail backup + Maildir conversion for one account."""
from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.backup_batch_registry import maybe_dispatch_next_gmail_in_wave
from app.services.backup_engine import (
    mark_gmail_backup_log_failed_on_worker_crash,
    run_gmail_backup,
)
from app.services.backup_job_context import load_task_account_for_backup
from app.workers.celery_app import celery_app
from app.workers.session import run_async, with_session

logger = logging.getLogger(__name__)

_SETTINGS = get_settings()
_GMAIL_TASK_KW: dict[str, float | int] = {}
if _SETTINGS.celery_backup_gmail_soft_time_limit_seconds > 0:
    _GMAIL_TASK_KW["soft_time_limit"] = _SETTINGS.celery_backup_gmail_soft_time_limit_seconds
if _SETTINGS.celery_backup_gmail_time_limit_seconds > 0:
    _GMAIL_TASK_KW["time_limit"] = _SETTINGS.celery_backup_gmail_time_limit_seconds


async def _execute(
    task_id: str, account_id: str, celery_task_id: str, run_batch_id: str | None
) -> dict[str, Any]:
    batch_uuid: uuid.UUID | None = None
    if run_batch_id:
        try:
            batch_uuid = uuid.UUID(run_batch_id)
        except ValueError:
            batch_uuid = None

    async def inner(db: AsyncSession) -> dict[str, Any]:
        pair = await load_task_account_for_backup(
            db,
            task_id=uuid.UUID(task_id),
            account_id=uuid.UUID(account_id),
        )
        if pair is None:
            return {"ok": False, "error": "task_account_not_eligible"}
        task, account = pair
        if batch_uuid is None and run_batch_id:
            return {"ok": False, "error": "invalid_batch_id"}
        logger.info(
            "backup_gmail start task_id=%s account_id=%s email=%s",
            task_id,
            account_id,
            account.email,
        )
        log = await run_gmail_backup(
            db,
            task=task,
            account=account,
            celery_task_id=celery_task_id,
            run_batch_id=batch_uuid,
        )
        logger.info(
            "backup_gmail done log_id=%s status=%s",
            log.id,
            log.status,
        )
        return {"ok": True, "log_id": str(log.id), "status": log.status}

    try:
        return await with_session(inner)
    except Exception as exc:
        logger.exception(
            "backup_gmail error task_id=%s account_id=%s celery_id=%s",
            task_id,
            account_id,
            celery_task_id,
        )
        try:

            async def _recover(db: AsyncSession) -> None:
                await mark_gmail_backup_log_failed_on_worker_crash(
                    db,
                    task_id=uuid.UUID(task_id),
                    account_id=uuid.UUID(account_id),
                    celery_task_id=celery_task_id,
                    error_summary=str(exc),
                )

            await with_session(_recover)
        except Exception:
            logger.exception("backup_gmail could not mark log as failed (task_id=%s)", task_id)
        raise
    finally:
        if batch_uuid is not None:
            await maybe_dispatch_next_gmail_in_wave(
                task_id=task_id, batch_id=str(batch_uuid)
            )


@celery_app.task(bind=True, name="app.workers.tasks.backup_gmail.run", **_GMAIL_TASK_KW)
def run(self, task_id: str, account_id: str, run_batch_id: str | None = None) -> dict[str, Any]:
    return run_async(_execute(task_id, account_id, self.request.id, run_batch_id))
