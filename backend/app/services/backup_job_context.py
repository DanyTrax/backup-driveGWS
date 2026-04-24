"""Resolución de tarea + cuenta para un job de backup (siempre vía definición en ``backup_tasks``)."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.accounts import GwAccount
from app.models.tasks import BackupTask


async def load_task_account_for_backup(
    db: AsyncSession,
    *,
    task_id: uuid.UUID,
    account_id: uuid.UUID,
) -> tuple[BackupTask, GwAccount] | None:
    """Carga la tarea con sus cuentas enlazadas y la cuenta.

    Devuelve ``None`` si la tarea no existe o **no está habilitada**, si la cuenta no existe, si la
    cuenta **no** está asignada a la tarea en ``backup_task_accounts``, o si
    ``gw_accounts.is_backup_enabled`` es falso. Ningún backup debe ejecutarse fuera de ese vínculo.
    """
    stmt = (
        select(BackupTask)
        .options(selectinload(BackupTask.accounts))
        .where(BackupTask.id == task_id)
    )
    task = (await db.execute(stmt)).scalar_one_or_none()
    if task is None:
        return None
    account = (
        await db.execute(select(GwAccount).where(GwAccount.id == account_id))
    ).scalar_one_or_none()
    if account is None:
        return None
    assigned = {a.id for a in (task.accounts or [])}
    if account.id not in assigned:
        return None
    if not account.is_backup_enabled:
        return None
    return task, account
