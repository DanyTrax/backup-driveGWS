"""Evita lanzar dos backups del mismo tipo (Gmail / Drive) para la misma tarea y cuenta."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import BackupScope, BackupStatus
from app.models.tasks import BackupLog

# Estados considerados «en curso» para deduplicar encolados.
_ACTIVE: tuple[str, ...] = (
    BackupStatus.PENDING.value,
    BackupStatus.QUEUED.value,
    BackupStatus.RUNNING.value,
)


def drive_scope_stored_in_log(_task_scope: str) -> str:
    """Siempre coincide con ``run_drive_backup`` → ``BackupScope.DRIVE_ROOT`` en el log."""
    return BackupScope.DRIVE_ROOT.value


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
