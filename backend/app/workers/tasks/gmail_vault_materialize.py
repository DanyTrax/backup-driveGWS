"""Celery: materialización de ZIPs vault Gmail en disco local (Fase 5)."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.gmail_vault_materialize_service import run_materialization_job
from app.workers.celery_app import celery_app
from app.workers.session import run_async, with_session


async def _execute(session_id: str, celery_task_id: str) -> dict[str, Any]:
    async def inner(db: AsyncSession) -> dict[str, Any]:
        await run_materialization_job(db, uuid.UUID(session_id), celery_task_id)
        return {"ok": True, "session_id": session_id}

    return await with_session(inner)


@celery_app.task(bind=True, name="app.workers.tasks.gmail_vault_materialize.run")
def run(self, session_id: str) -> dict[str, Any]:
    return run_async(_execute(session_id, self.request.id))
