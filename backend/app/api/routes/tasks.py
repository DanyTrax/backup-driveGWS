"""CRUD and dispatch for backup tasks."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import (
    get_client_ip,
    get_db,
    get_user_agent,
    require_any_permission,
    require_permission,
)
from app.models.accounts import GwAccount
from app.models.enums import AuditAction, BackupScope
from app.models.tasks import BackupTask, backup_task_accounts
from app.models.users import SysUser
from app.schemas.tasks import RunEstimateOut, RunResultOut, TaskCreate, TaskOut, TaskUpdate
from app.core.logging import get_logger
from app.services.backup_batch_registry import store_batch_celery_ids
from app.services.audit_service import record_audit
from app.services.backup_estimate_service import run_estimate_payload

router = APIRouter(prefix="/tasks", tags=["tasks"])
log = get_logger("tasks")


def _to_out(t: BackupTask, *, account_ids: list[str] | None = None) -> TaskOut:
    ids = account_ids if account_ids is not None else [str(a.id) for a in (t.accounts or [])]
    return TaskOut(
        id=str(t.id),
        name=t.name,
        description=t.description,
        is_enabled=t.is_enabled,
        scope=t.scope,
        mode=t.mode,
        schedule_kind=t.schedule_kind,
        cron_expression=t.cron_expression,
        run_at_hour=t.run_at_hour,
        run_at_minute=t.run_at_minute,
        timezone=t.timezone,
        retention_policy=t.retention_policy_json or {},
        filters=t.filters_json or {},
        notify_channels=t.notify_channels_json or {},
        dry_run=t.dry_run,
        checksum_enabled=t.checksum_enabled,
        max_parallel_accounts=t.max_parallel_accounts,
        account_ids=ids,
        last_run_at=t.last_run_at,
        last_status=t.last_status,
        created_at=t.created_at,
    )


async def _load(db: AsyncSession, task_id: uuid.UUID) -> BackupTask:
    stmt = (
        select(BackupTask)
        .options(selectinload(BackupTask.accounts))
        .where(BackupTask.id == task_id)
    )
    t = (await db.execute(stmt)).scalar_one_or_none()
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "task_not_found")
    return t


async def _junction_account_ids(db: AsyncSession, task_id: uuid.UUID) -> list[str]:
    stmt = select(backup_task_accounts.c.account_id).where(backup_task_accounts.c.task_id == task_id)
    rows = (await db.execute(stmt)).all()
    return [str(r[0]) for r in rows]


async def _sync_accounts(db: AsyncSession, task: BackupTask, account_ids: list[str]) -> None:
    """Persiste M2M solo vía SQL Core (evita greenlet/async al asignar task.accounts)."""
    await db.flush()
    tid = task.id
    await db.execute(delete(backup_task_accounts).where(backup_task_accounts.c.task_id == tid))
    if not account_ids:
        await db.flush()
        return
    raw = [(a or "").strip() for a in account_ids if (a or "").strip()]
    try:
        uids = list(dict.fromkeys(uuid.UUID(x) for x in raw))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_account_id") from exc
    stmt = select(GwAccount.id, GwAccount.email, GwAccount.is_backup_enabled).where(GwAccount.id.in_(uids))
    rows = (await db.execute(stmt)).all()
    by_id: dict[uuid.UUID, tuple[str, bool]] = {r[0]: (r[1], r[2]) for r in rows}
    if len(by_id) != len(uids):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unknown_account_ids")
    disabled = [by_id[uid][0] for uid in uids if by_id[uid][1] is not True]
    if disabled:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"error": "accounts_backup_not_enabled", "emails": disabled},
        )
    for uid in uids:
        await db.execute(insert(backup_task_accounts).values(task_id=tid, account_id=uid))
    await db.flush()


@router.get("", response_model=list[TaskOut])
async def list_tasks(
    db: AsyncSession = Depends(get_db),
    _u: SysUser = Depends(require_permission("tasks.view")),
) -> list[TaskOut]:
    stmt = (
        select(BackupTask)
        .options(selectinload(BackupTask.accounts))
        .order_by(BackupTask.created_at.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [_to_out(t) for t in rows]


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("tasks.create")),
) -> TaskOut:
    try:
        task = BackupTask(
            name=payload.name,
            description=payload.description,
            is_enabled=payload.is_enabled,
            scope=payload.scope.value,
            mode=payload.mode.value,
            schedule_kind=payload.schedule_kind.value,
            cron_expression=payload.cron_expression,
            run_at_hour=payload.run_at_hour,
            run_at_minute=payload.run_at_minute,
            timezone=payload.timezone,
            retention_policy_json=payload.retention_policy,
            filters_json=payload.filters,
            notify_channels_json=payload.notify_channels,
            dry_run=payload.dry_run,
            checksum_enabled=payload.checksum_enabled,
            max_parallel_accounts=payload.max_parallel_accounts,
            created_by_user_id=current.id,
        )
        db.add(task)
        await db.flush()
        await _sync_accounts(db, task, payload.account_ids)
        await record_audit(
            db,
            action=AuditAction.SETTING_CHANGED,
            actor_user_id=current.id,
            actor_label=current.email,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
            target_table="backup_tasks",
            target_id=str(task.id),
            message="task_created",
        )
        await db.commit()
        t = (await db.execute(select(BackupTask).where(BackupTask.id == task.id))).scalar_one()
        return _to_out(t, account_ids=await _junction_account_ids(db, task.id))
    except HTTPException:
        await db.rollback()
        raise
    except Exception as exc:
        await db.rollback()
        log.exception("task_create_failed", error=str(exc))
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "task_create_failed", "reason": str(exc)[:500]},
        ) from exc


@router.patch("/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: uuid.UUID,
    payload: TaskUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("tasks.edit")),
) -> TaskOut:
    task = await _load(db, task_id)
    task.name = payload.name
    task.description = payload.description
    task.is_enabled = payload.is_enabled
    task.scope = payload.scope.value
    task.mode = payload.mode.value
    task.schedule_kind = payload.schedule_kind.value
    task.cron_expression = payload.cron_expression
    task.run_at_hour = payload.run_at_hour
    task.run_at_minute = payload.run_at_minute
    task.timezone = payload.timezone
    task.retention_policy_json = payload.retention_policy
    task.filters_json = payload.filters
    task.notify_channels_json = payload.notify_channels
    task.dry_run = payload.dry_run
    task.checksum_enabled = payload.checksum_enabled
    task.max_parallel_accounts = payload.max_parallel_accounts
    await _sync_accounts(db, task, payload.account_ids)

    await record_audit(
        db,
        action=AuditAction.SETTING_CHANGED,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        target_table="backup_tasks",
        target_id=str(task.id),
        message="task_updated",
    )
    await db.commit()
    t = (await db.execute(select(BackupTask).where(BackupTask.id == task_id))).scalar_one()
    return _to_out(t, account_ids=await _junction_account_ids(db, task_id))


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def delete_task(
    task_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("tasks.delete")),
) -> None:
    task = await _load(db, task_id)
    await record_audit(
        db,
        action=AuditAction.SETTING_CHANGED,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        target_table="backup_tasks",
        target_id=str(task.id),
        message="task_deleted",
    )
    await db.delete(task)
    await db.commit()


@router.get(
    "/{task_id}/run-estimate",
    response_model=RunEstimateOut,
    summary="Estimación aproximada de duración antes de ejecutar",
)
async def run_task_estimate(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _u: SysUser = Depends(require_any_permission("tasks.run", "tasks.view")),
) -> RunEstimateOut:
    """Heurística según caché de cuenta y último log Drive; no es compromiso de tiempo real."""
    task = await _load(db, task_id)
    data = await run_estimate_payload(db, task)
    return RunEstimateOut.model_validate(data)


@router.post("/{task_id}/run", response_model=RunResultOut)
async def run_task(
    task_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("tasks.run")),
) -> RunResultOut:
    from app.workers.tasks.backup_drive import run as run_drive
    from app.workers.tasks.backup_gmail import run as run_gmail

    task = await _load(db, task_id)
    accounts = [a for a in (task.accounts or []) if a.is_backup_enabled]
    if not accounts:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no_enabled_accounts")

    batch_id = uuid.uuid4()
    batch_str = str(batch_id)
    celery_ids: list[str] = []
    for account in accounts:
        if task.scope in (BackupScope.DRIVE_ROOT.value, BackupScope.DRIVE_COMPUTADORAS.value, BackupScope.FULL.value):
            res = run_drive.delay(str(task.id), str(account.id), batch_str)
            celery_ids.append(res.id)
        if task.scope in (BackupScope.GMAIL.value, BackupScope.FULL.value):
            res = run_gmail.delay(str(task.id), str(account.id), batch_str)
            celery_ids.append(res.id)

    await store_batch_celery_ids(batch_str, celery_ids)

    await record_audit(
        db,
        action=AuditAction.BACKUP_TRIGGERED,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        target_table="backup_tasks",
        target_id=str(task.id),
        metadata={"celery_ids": celery_ids, "run_batch_id": batch_str},
    )
    await db.commit()
    return RunResultOut(queued=len(celery_ids), celery_ids=celery_ids, batch_id=batch_str)
