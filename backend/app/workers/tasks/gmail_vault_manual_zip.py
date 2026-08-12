"""Celery: subir un ZIP vault desde el export GYB ya en disco (operación manual panel)."""
from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tasks import BackupLog
from app.services.gmail_vault_manual_zip_service import execute_manual_gmail_vault_zip
from app.workers.celery_app import celery_app
from app.workers.session import run_async, with_session

logger = logging.getLogger(__name__)


async def _execute(log_id: str, celery_task_id: str) -> dict[str, Any]:
    async def inner(db: AsyncSession) -> dict[str, Any]:
        await execute_manual_gmail_vault_zip(
            db,
            log_id=uuid.UUID(log_id),
            celery_task_id=celery_task_id,
        )
        row = await db.get(BackupLog, uuid.UUID(log_id))
        status = row.status if row is not None else "missing"
        logger.info(
            "gmail_vault_manual_zip finished log_id=%s status=%s celery=%s",
            log_id,
            status,
            celery_task_id,
        )
        return {"ok": True, "log_id": log_id, "status": status}

    return await with_session(inner)


@celery_app.task(bind=True, name="app.workers.tasks.gmail_vault_manual_zip.run")
def run(self, log_id: str) -> dict[str, Any]:
    rid = getattr(self.request, "id", None) or ""
    logger.info("gmail_vault_manual_zip start log_id=%s", log_id)
    out = run_async(_execute(log_id, rid))
    logger.info("gmail_vault_manual_zip done log_id=%s", log_id)
    return out
