"""Backup log browsing and WebSocket progress stream."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, WebSocket, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_client_ip,
    get_current_user_ws,
    get_db,
    get_user_agent,
    require_permission,
)
from app.core.database import AsyncSessionLocal
from app.models.accounts import GwAccount
from app.models.enums import AuditAction
from app.models.tasks import BackupLog, BackupTask
from app.models.users import SysUser
from app.schemas.tasks import BackupLogOut
from app.services.audit_service import record_audit
from app.services.backup_batch_registry import cancel_entire_batch
from app.services.backup_engine import cancel_backup
from app.services.progress_bus import last_event, subscribe

router = APIRouter(prefix="/backup", tags=["backup"])


def _to_out(
    l: BackupLog,
    *,
    task_name: str | None = None,
    account_email: str | None = None,
) -> BackupLogOut:
    return BackupLogOut(
        id=str(l.id),
        task_id=str(l.task_id),
        account_id=str(l.account_id),
        run_batch_id=str(l.run_batch_id) if l.run_batch_id else None,
        status=l.status,
        scope=l.scope,
        mode=l.mode,
        started_at=l.started_at,
        finished_at=l.finished_at,
        bytes_transferred=l.bytes_transferred,
        files_count=l.files_count,
        messages_count=l.messages_count,
        errors_count=l.errors_count,
        celery_task_id=l.celery_task_id,
        sha256_manifest_path=l.sha256_manifest_path,
        destination_path=l.destination_path,
        error_summary=l.error_summary,
        task_name=task_name,
        account_email=account_email,
    )


@router.get("/logs", response_model=list[BackupLogOut])
async def list_logs(
    task_id: uuid.UUID | None = None,
    account_id: uuid.UUID | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _u: SysUser = Depends(require_permission("logs.view")),
) -> list[BackupLogOut]:
    stmt = (
        select(BackupLog, BackupTask.name, GwAccount.email)
        .join(BackupTask, BackupLog.task_id == BackupTask.id)
        .join(GwAccount, BackupLog.account_id == GwAccount.id)
        .order_by(BackupLog.started_at.desc().nullslast())
        .limit(limit)
        .offset(offset)
    )
    if task_id:
        stmt = stmt.where(BackupLog.task_id == task_id)
    if account_id:
        stmt = stmt.where(BackupLog.account_id == account_id)
    if status_filter:
        stmt = stmt.where(BackupLog.status == status_filter)
    rows = (await db.execute(stmt)).all()
    return [_to_out(log, task_name=name, account_email=email) for log, name, email in rows]


@router.get("/logs/{log_id}", response_model=BackupLogOut)
async def get_log(
    log_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _u: SysUser = Depends(require_permission("logs.view")),
) -> BackupLogOut:
    row = (
        (
            await db.execute(
                select(BackupLog, BackupTask.name, GwAccount.email)
                .join(BackupTask, BackupLog.task_id == BackupTask.id)
                .join(GwAccount, BackupLog.account_id == GwAccount.id)
                .where(BackupLog.id == log_id)
            )
        )
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "log_not_found")
    log, task_name, account_email = row
    return _to_out(log, task_name=task_name, account_email=account_email)


@router.post(
    "/batches/{batch_id}/cancel",
    status_code=status.HTTP_200_OK,
)
async def cancel_batch(
    batch_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("tasks.run")),
) -> dict[str, int]:
    """Cancela todo un lote (revoca Celery + marca logs en curso). Las cuentas ya finalizadas no cambian."""
    stats = await cancel_entire_batch(db, batch_id=batch_id)
    await record_audit(
        db,
        action=AuditAction.BACKUP_CANCELLED,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        target_table="backup_logs",
        target_id=str(batch_id),
        message="batch_cancelled",
        metadata=stats,
    )
    await db.commit()
    return stats


@router.post(
    "/logs/{log_id}/cancel",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def cancel_log(
    log_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("tasks.run")),
) -> None:
    ok = await cancel_backup(db, log_id)
    if not ok:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "cannot_cancel")
    await record_audit(
        db,
        action=AuditAction.BACKUP_CANCELLED,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        target_table="backup_logs",
        target_id=str(log_id),
    )
    await db.commit()


@router.websocket("/ws/progress/{log_id}")
async def ws_progress(websocket: WebSocket, log_id: uuid.UUID, token: str | None = None) -> None:
    async with AsyncSessionLocal() as db:
        user = await get_current_user_ws(websocket, db, token)
    if user is None:
        await websocket.close(code=4401)
        return
    await websocket.accept()

    snapshot = await last_event(str(log_id))
    if snapshot:
        await websocket.send_json(snapshot)

    try:
        async for event in subscribe(str(log_id)):
            await websocket.send_json(event)
    except Exception:  # noqa: BLE001
        await websocket.close()
