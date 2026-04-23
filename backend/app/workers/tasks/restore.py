"""Celery tasks for Drive and Gmail restores."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.restore import RestoreJob
from app.services.restore_engine import (
    restore_drive_job,
    restore_gmail_job,
)
from app.workers.celery_app import celery_app
from app.workers.session import run_async, with_session


@celery_app.task(bind=True, name="app.workers.tasks.restore.drive")
def drive(self, job_id: str) -> dict[str, Any]:
    async def inner(db: AsyncSession) -> dict[str, Any]:
        stmt = select(RestoreJob).where(RestoreJob.id == uuid.UUID(job_id))
        job = (await db.execute(stmt)).scalar_one_or_none()
        if job is None:
            return {"ok": False, "error": "not_found"}
        return await restore_drive_job(db, job=job, celery_task_id=self.request.id)

    return run_async(with_session(inner))


@celery_app.task(bind=True, name="app.workers.tasks.restore.gmail")
def gmail(self, job_id: str) -> dict[str, Any]:
    async def inner(db: AsyncSession) -> dict[str, Any]:
        stmt = select(RestoreJob).where(RestoreJob.id == uuid.UUID(job_id))
        job = (await db.execute(stmt)).scalar_one_or_none()
        if job is None:
            return {"ok": False, "error": "not_found"}
        return await restore_gmail_job(db, job=job, celery_task_id=self.request.id)

    return run_async(with_session(inner))
