"""Redis: señales de cancelación por log, por lote, e ids de Celery del lote."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import get_redis
from app.models.enums import BackupStatus
from app.models.tasks import BackupLog
from app.services.progress_bus import publish


async def store_batch_celery_ids(batch_id: str, celery_ids: list[str]) -> None:
    if not celery_ids:
        return
    r = get_redis()
    await r.setex(f"backup:batch:{batch_id}:celery_ids", 7200, json.dumps(celery_ids))


async def fetch_batch_celery_ids(batch_id: str) -> list[str]:
    raw = await get_redis().get(f"backup:batch:{batch_id}:celery_ids")
    if not raw:
        return []
    return json.loads(raw)


async def set_batch_cancelled(batch_id: str) -> None:
    await get_redis().setex(f"backup:batch_cancel:{batch_id}", 7200, "1")


async def is_batch_cancelled(batch_id: str) -> bool:
    return (await get_redis().get(f"backup:batch_cancel:{batch_id}")) == "1"


async def set_log_cancelled(log_id: str) -> None:
    await get_redis().setex(f"backup:cancel:{log_id}", 7200, "1")


async def is_log_cancelled(log_id: str) -> bool:
    return (await get_redis().get(f"backup:cancel:{log_id}")) == "1"


async def cancel_entire_batch(
    db: AsyncSession,
    *,
    batch_id: uuid.UUID,
) -> dict[str, int]:
    """Marca el lote cancelado, revoca jobs Celery encolados y cancela logs aún en curso."""
    from app.workers.celery_app import celery_app

    bid = str(batch_id)
    await set_batch_cancelled(bid)
    celery_ids = await fetch_batch_celery_ids(bid)
    revoked = 0
    for cid in celery_ids:
        celery_app.control.revoke(cid, terminate=True)
        revoked += 1

    stmt = select(BackupLog).where(
        BackupLog.run_batch_id == batch_id,
        BackupLog.status.in_(
            [
                BackupStatus.RUNNING.value,
                BackupStatus.PENDING.value,
                BackupStatus.QUEUED.value,
            ]
        ),
    )
    rows = (await db.execute(stmt)).scalars().all()
    cancelled_logs = 0
    for log in rows:
        await set_log_cancelled(str(log.id))
        log.status = BackupStatus.CANCELLED.value
        log.finished_at = datetime.now(timezone.utc)
        prev = (log.error_summary or "").strip()
        log.error_summary = (prev + "\n" if prev else "") + "batch_cancelled"
        await publish(str(log.id), {"stage": "cancelled", "batch": True})
        cancelled_logs += 1
    await db.flush()
    return {"revoked_celery": revoked, "cancelled_logs": cancelled_logs}
