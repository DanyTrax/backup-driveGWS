"""Tarea ``BackupTask`` sintética para operaciones del panel que deben figurar en ``backup_logs``.

Celery Beat no debe disparar estas tareas (``is_enabled=False``, ``schedule_kind=manual``).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import BackupMode, BackupScope, ScheduleKind
from app.models.tasks import BackupTask

PANEL_MAILDIR_GYB_REBUILD_TASK_NAME = "[Sistema] Panel: Maildir desde GYB"
PANEL_GYB_VAULT_RESTORE_TASK_NAME = "[Sistema] Panel: GYB desde bóveda Drive"


async def get_or_create_panel_maildir_gyb_rebuild_task(db: AsyncSession) -> BackupTask:
    stmt = select(BackupTask).where(BackupTask.name == PANEL_MAILDIR_GYB_REBUILD_TASK_NAME).limit(1)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is not None:
        return row
    task = BackupTask(
        name=PANEL_MAILDIR_GYB_REBUILD_TASK_NAME,
        description=(
            "Registro en Logs / Historial de ejecuciones cuando un admin "
            "reconstruye Maildir desde el trabajo GYB local (panel). "
            "No ejecutar desde tareas programadas."
        ),
        is_enabled=False,
        scope=BackupScope.GMAIL.value,
        mode=BackupMode.INCREMENTAL.value,
        schedule_kind=ScheduleKind.MANUAL.value,
        cron_expression=None,
        run_at_hour=None,
        run_at_minute=None,
        timezone="America/Bogota",
        retention_policy_json={},
        filters_json={"panel_synthetic": True, "operation": "maildir_rebuild_from_local_gyb"},
        notify_channels_json={},
        dry_run=False,
        checksum_enabled=True,
        max_parallel_accounts=1,
        created_by_user_id=None,
    )
    db.add(task)
    await db.flush()
    return task


async def get_or_create_panel_gyb_vault_restore_task(db: AsyncSession) -> BackupTask:
    stmt = (
        select(BackupTask).where(BackupTask.name == PANEL_GYB_VAULT_RESTORE_TASK_NAME).limit(1)
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is not None:
        return row
    task = BackupTask(
        name=PANEL_GYB_VAULT_RESTORE_TASK_NAME,
        description=(
            "Registro en Historial cuando un admin trae el export GYB desde "
            "1-GMAIL/gyb_mbox en Drive a la carpeta de trabajo local (rclone). "
            "No ejecutar desde tareas programadas."
        ),
        is_enabled=False,
        scope=BackupScope.GMAIL.value,
        mode=BackupMode.INCREMENTAL.value,
        schedule_kind=ScheduleKind.MANUAL.value,
        cron_expression=None,
        run_at_hour=None,
        run_at_minute=None,
        timezone="America/Bogota",
        retention_policy_json={},
        filters_json={"panel_synthetic": True, "operation": "gyb_restore_from_vault"},
        notify_channels_json={},
        dry_run=False,
        checksum_enabled=True,
        max_parallel_accounts=1,
        created_by_user_id=None,
    )
    db.add(task)
    await db.flush()
    return task
