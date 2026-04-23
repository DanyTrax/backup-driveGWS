"""Celery tasks for async notification fan-out."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import NotificationSeverity
from app.models.users import SysUser
from app.services.notification_service import broadcast, notify_user
from app.workers.celery_app import celery_app
from app.workers.session import run_async, with_session


@celery_app.task(name="app.workers.tasks.notify.broadcast")
def broadcast_task(
    *,
    role_filter: str | None,
    category: str,
    title: str,
    body: str | None = None,
    severity: str = "info",
) -> dict[str, Any]:
    async def inner(db: AsyncSession) -> dict[str, Any]:
        count = await broadcast(
            db,
            role_filter=role_filter,
            category=category,
            title=title,
            body=body,
            severity=NotificationSeverity(severity),
        )
        return {"ok": True, "count": count}

    return run_async(with_session(inner))


@celery_app.task(name="app.workers.tasks.notify.user")
def user_task(
    user_id: str,
    *,
    category: str,
    title: str,
    body: str | None = None,
    severity: str = "info",
) -> dict[str, Any]:
    async def inner(db: AsyncSession) -> dict[str, Any]:
        user = (
            await db.execute(select(SysUser).where(SysUser.id == uuid.UUID(user_id)))
        ).scalar_one_or_none()
        if user is None:
            return {"ok": False, "error": "not_found"}
        await notify_user(
            db,
            user=user,
            category=category,
            title=title,
            body=body,
            severity=NotificationSeverity(severity),
        )
        return {"ok": True}

    return run_async(with_session(inner))
