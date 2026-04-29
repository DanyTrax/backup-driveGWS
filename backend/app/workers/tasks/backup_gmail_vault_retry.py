"""Celery: reintentar solo la subida Gmail al vault (1-GMAIL/gyb_mbox)."""
from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.backup_engine import retry_gmail_vault_push
from app.workers.celery_app import celery_app
from app.workers.session import run_async, with_session

logger = logging.getLogger(__name__)


async def _execute(log_id: str, celery_task_id: str) -> dict[str, Any]:
    async def inner(db: AsyncSession) -> dict[str, Any]:
        try:
            log = await retry_gmail_vault_push(db, uuid.UUID(log_id), celery_task_id)
        except ValueError as exc:
            logger.warning(
                "backup_gmail_vault_retry skipped log_id=%s: %s",
                log_id,
                exc,
            )
            return {"ok": False, "error": str(exc)}
        logger.info(
            "backup_gmail_vault_retry done log_id=%s status=%s",
            log.id,
            log.status,
        )
        return {"ok": True, "log_id": str(log.id), "status": log.status}

    return await with_session(inner)


@celery_app.task(bind=True, name="app.workers.tasks.backup_gmail_vault_retry.run")
def run(self, log_id: str) -> dict[str, Any]:
    return run_async(_execute(log_id, self.request.id))
