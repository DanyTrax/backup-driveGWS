"""Backup log browsing and WebSocket progress stream."""
from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, WebSocket, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_client_ip,
    get_current_user_ws,
    get_db,
    get_user_agent,
    require_permission,
)
from app.core.database import AsyncSessionLocal
from app.core.redis_client import get_redis
from app.models.accounts import GwAccount
from app.models.enums import AuditAction, BackupScope, BackupStatus
from app.models.tasks import BackupLog, BackupTask
from app.models.users import SysUser
from app.schemas.tasks import BackupLogBulkDeleteIn, BackupLogBulkDeleteOut, BackupLogOut
from app.services.audit_service import record_audit
from app.services.backup_batch_registry import cancel_entire_batch
from app.services.backup_concurrency_service import active_backup_log_id
from app.services.backup_engine import (
    cancel_backup,
    gmail_log_vault_retry_reason,
    gyb_workdir_has_export,
)
from app.services.progress_bus import last_event, subscribe

router = APIRouter(prefix="/backup", tags=["backup"])

logger = logging.getLogger(__name__)


async def _safe_last_event(log_id: str) -> dict[str, Any] | None:
    """No debe tumbar GET /logs/{id} si Redis no responde o falta en el entorno."""
    try:
        return await last_event(log_id)
    except Exception as exc:
        logger.warning(
            "Progreso en vivo (Redis) no disponible para log_id=%s: %s",
            log_id,
            exc,
            exc_info=True,
        )
        return None


def _logs_list_stmt(
    *,
    task_id: uuid.UUID | None,
    account_id: uuid.UUID | None,
    status_filter: str | None,
    limit: int,
    offset: int,
):
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
    return stmt


async def _purge_progress_for_logs(log_ids: list[uuid.UUID]) -> None:
    if not log_ids:
        return
    try:
        r = get_redis()
        keys = [f"progress:last:{lid}" for lid in log_ids]
        await r.delete(*keys)
    except Exception as exc:
        logger.warning(
            "No se pudo limpiar claves de progreso Redis al borrar logs: %s",
            exc,
            exc_info=True,
        )


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
        detail_log_path=l.detail_log_path,
        gmail_maildir_ready_at=l.gmail_maildir_ready_at,
        gmail_vault_completed_at=l.gmail_vault_completed_at,
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
    stmt = _logs_list_stmt(
        task_id=task_id,
        account_id=account_id,
        status_filter=status_filter,
        limit=limit,
        offset=offset,
    )
    rows = (await db.execute(stmt)).all()
    return [_to_out(log, task_name=name, account_email=email) for log, name, email in rows]


@router.get("/logs/export.pdf")
async def export_logs_pdf(
    task_id: uuid.UUID | None = None,
    account_id: uuid.UUID | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(500, le=500),
    db: AsyncSession = Depends(get_db),
    _u: SysUser = Depends(require_permission("logs.export")),
) -> Response:
    stmt = _logs_list_stmt(
        task_id=task_id,
        account_id=account_id,
        status_filter=status_filter,
        limit=limit,
        offset=0,
    )
    rows = (await db.execute(stmt)).all()
    outs = [_to_out(log, task_name=name, account_email=email) for log, name, email in rows]
    parts: list[str] = []
    if status_filter:
        parts.append(f"estado={status_filter}")
    if task_id:
        parts.append(f"task_id={task_id}")
    if account_id:
        parts.append(f"account_id={account_id}")
    filter_note = ", ".join(parts) if parts else None
    try:
        from app.services.backup_logs_pdf import render_backup_logs_pdf
    except ImportError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="pdf_library_missing: instale fpdf2 en la imagen/backend (pip install fpdf2)",
        ) from exc
    try:
        pdf_bytes = render_backup_logs_pdf(
            outs,
            filter_note=filter_note,
            generated_at=datetime.now(timezone.utc),
        )
    except RuntimeError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    fname = f"backup-logs-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/logs/bulk-delete", response_model=BackupLogBulkDeleteOut)
async def bulk_delete_logs(
    payload: BackupLogBulkDeleteIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("logs.delete")),
) -> BackupLogBulkDeleteOut:
    if not payload.log_ids:
        return BackupLogBulkDeleteOut(deleted=0, skipped_running=[], not_found=[])

    wanted = list(dict.fromkeys(payload.log_ids))
    stmt = select(BackupLog).where(BackupLog.id.in_(wanted))
    found = (await db.execute(stmt)).scalars().all()
    by_id = {row.id: row for row in found}
    not_found = [str(i) for i in wanted if i not in by_id]
    skipped_running = [str(row.id) for row in found if row.status == BackupStatus.RUNNING.value]
    to_delete = [row.id for row in found if row.status != BackupStatus.RUNNING.value]
    if to_delete:
        await db.execute(delete(BackupLog).where(BackupLog.id.in_(to_delete)))
        await _purge_progress_for_logs(to_delete)
    await record_audit(
        db,
        action=AuditAction.BACKUP_LOG_DELETED,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        target_table="backup_logs",
        target_id=None,
        message="bulk_delete",
        metadata={
            "deleted": len(to_delete),
            "skipped_running": skipped_running,
            "not_found": not_found,
        },
    )
    await db.commit()
    return BackupLogBulkDeleteOut(
        deleted=len(to_delete),
        skipped_running=skipped_running,
        not_found=not_found,
    )


@router.delete(
    "/logs/{log_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def delete_log(
    log_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("logs.delete")),
) -> None:
    log = await db.get(BackupLog, log_id)
    if log is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "log_not_found")
    if log.status == BackupStatus.RUNNING.value:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"error": "log_running"},
        )
    await db.execute(delete(BackupLog).where(BackupLog.id == log_id))
    await _purge_progress_for_logs([log_id])
    await record_audit(
        db,
        action=AuditAction.BACKUP_LOG_DELETED,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        target_table="backup_logs",
        target_id=str(log_id),
    )
    await db.commit()


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
    base = _to_out(log, task_name=task_name, account_email=account_email)
    snap = await _safe_last_event(str(log_id))
    return base.model_copy(update={"live_progress": snap})


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


@router.post(
    "/logs/{log_id}/retry-gmail-vault",
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_gmail_vault(
    log_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("tasks.run")),
) -> dict[str, str | bool]:
    """Reintenta solo la subida del export GYB a 1-GMAIL/gyb_mbox (Maildir local ya consolidado)."""
    log = await db.get(BackupLog, log_id)
    if log is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "log_not_found"})
    task = await db.get(BackupTask, log.task_id)
    account = await db.get(GwAccount, log.account_id)
    if task is None or account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "task_or_account_missing"})

    reason = gmail_log_vault_retry_reason(log, task)
    if reason:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"error": reason})

    work_root = Path(f"/var/msa/work/gmail/{account.email}")
    if not gyb_workdir_has_export(work_root):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"error": "gyb_workdir_empty"},
        )
    if not (account.drive_vault_folder_id or "").strip():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"error": "missing_vault_folder"},
        )

    dup = await active_backup_log_id(
        db,
        task_id=log.task_id,
        account_id=log.account_id,
        log_scope=BackupScope.GMAIL.value,
    )
    if dup is not None and dup != log.id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"error": "active_gmail_backup_exists", "active_log_id": str(dup)},
        )

    from app.workers.tasks.backup_gmail_vault_retry import run as retry_gmail_vault_task

    async_result = retry_gmail_vault_task.delay(str(log_id))
    await record_audit(
        db,
        action=AuditAction.BACKUP_TRIGGERED,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        target_table="backup_logs",
        target_id=str(log_id),
        message="gmail_vault_retry_queued",
        metadata={"celery_id": async_result.id},
    )
    await db.commit()
    return {"queued": True, "celery_id": async_result.id}


@router.websocket("/ws/progress/{log_id}")
async def ws_progress(websocket: WebSocket, log_id: uuid.UUID, token: str | None = None) -> None:
    async with AsyncSessionLocal() as db:
        user = await get_current_user_ws(websocket, db, token)
    if user is None:
        await websocket.close(code=4401)
        return
    await websocket.accept()

    snapshot = await _safe_last_event(str(log_id))
    if snapshot:
        await websocket.send_json(snapshot)

    try:
        async for event in subscribe(str(log_id)):
            await websocket.send_json(event)
    except Exception:  # noqa: BLE001
        await websocket.close()
