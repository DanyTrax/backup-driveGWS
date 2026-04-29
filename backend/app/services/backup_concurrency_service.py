"""Evita lanzar dos backups del mismo tipo (Gmail / Drive) para la misma tarea y cuenta."""

from __future__ import annotations

import hashlib
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import BackupStatus
from app.models.tasks import BackupLog

# Estados considerados «en curso» para deduplicar encolados.
_ACTIVE: tuple[str, ...] = (
    BackupStatus.PENDING.value,
    BackupStatus.QUEUED.value,
    BackupStatus.RUNNING.value,
)


def drive_scope_stored_in_log(task_scope: str) -> str:
    """Scope persistido en ``BackupLog`` (mismo string que la tarea: raíz vs Computadoras)."""
    return task_scope


async def active_backup_log_id(
    db: AsyncSession,
    *,
    task_id: uuid.UUID,
    account_id: uuid.UUID,
    log_scope: str,
) -> uuid.UUID | None:
    """Devuelve el id de un ``BackupLog`` activo si existe."""
    stmt = (
        select(BackupLog.id)
        .where(
            BackupLog.task_id == task_id,
            BackupLog.account_id == account_id,
            BackupLog.scope == log_scope,
            BackupLog.status.in_(_ACTIVE),
        )
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


def _advisory_int_pair(task_id: uuid.UUID, account_id: uuid.UUID, namespace: str) -> tuple[int, int]:
    """Dos int4 firmados para ``pg_advisory_xact_lock`` (estables por tarea/cuenta/ámbito)."""
    digest = hashlib.sha256(f"{task_id}:{account_id}:{namespace}".encode()).digest()
    k1 = int.from_bytes(digest[:4], "big", signed=True)
    k2 = int.from_bytes(digest[4:8], "big", signed=True)
    return k1, k2


async def acquire_backup_start_xact_lock(
    db: AsyncSession,
    *,
    task_id: uuid.UUID,
    account_id: uuid.UUID,
    namespace: str,
) -> None:
    """Bloquea hasta que otra transacción concurrente termine el check+insert del log.

    Evita condiciones de carrera donde dos workers pasan ``active_backup_log_id`` vacío y lanzan
    dos GYB para la misma tarea/cuenta. El cerrojo se libera al hacer commit/rollback de la transacción.
    """
    bind = db.get_bind()
    if bind is None or bind.dialect.name != "postgresql":
        return
    k1, k2 = _advisory_int_pair(task_id, account_id, namespace)
    await db.execute(text("SELECT pg_advisory_xact_lock(:k1, :k2)"), {"k1": k1, "k2": k2})
