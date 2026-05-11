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
from app.workers.celery_app import celery_app


async def store_batch_celery_ids(batch_id: str, celery_ids: list[str]) -> None:
    if not celery_ids:
        return
    r = get_redis()
    await r.setex(f"backup:batch:{batch_id}:celery_ids", 7200, json.dumps(celery_ids))


async def extend_batch_celery_ids(batch_id: str, more: list[str]) -> None:
    """Añade ids Celery (p. ej. segunda oleada al liberar hueco del wave Gmail)."""
    if not more:
        return
    r = get_redis()
    key = f"backup:batch:{batch_id}:celery_ids"
    raw = await r.get(key)
    cur: list[str] = json.loads(raw) if raw else []
    cur.extend(more)
    await r.setex(key, 7200, json.dumps(cur))


def _gmail_wave_queue_key(batch_id: str) -> str:
    return f"backup:wave:{batch_id}:gmail:accounts"


async def init_gmail_wave_queue(batch_id: str, pending_account_ids: list[str]) -> None:
    """Cuentas Gmail pendientes (FIFO); los primeros N ya se dispararon con Celery."""
    r = get_redis()
    key = _gmail_wave_queue_key(batch_id)
    await r.delete(key)
    if pending_account_ids:
        await r.rpush(key, *pending_account_ids)
        await r.expire(key, 7200)


async def pop_next_gmail_wave_account(batch_id: str) -> str | None:
    r = get_redis()
    raw = await r.lpop(_gmail_wave_queue_key(batch_id))
    if not raw:
        return None
    return raw.decode() if isinstance(raw, (bytes, bytearray)) else str(raw)


async def clear_gmail_wave_queue(batch_id: str) -> None:
    await get_redis().delete(_gmail_wave_queue_key(batch_id))


async def maybe_dispatch_next_gmail_in_wave(*, task_id: str, batch_id: str) -> None:
    """Al terminar un job Gmail (éxito o error), arranca el siguiente de la cola del lote."""
    if await is_batch_cancelled(batch_id):
        return
    next_acc = await pop_next_gmail_wave_account(batch_id)
    if not next_acc:
        return
    # send_task evita reimportar backup_gmail dentro del finally del mismo módulo (contexto async raro).
    res = celery_app.send_task(
        "app.workers.tasks.backup_gmail.run",
        args=[task_id, next_acc, batch_id],
    )
    await extend_batch_celery_ids(batch_id, [res.id])


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
    await clear_gmail_wave_queue(bid)
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
