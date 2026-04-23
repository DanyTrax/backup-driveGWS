"""Restore job endpoints (Drive / Gmail)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_client_ip,
    get_db,
    get_user_agent,
    require_permission,
)
from app.models.enums import AuditAction, RestoreScope, RestoreStatus
from app.models.restore import RestoreJob
from app.models.users import SysUser
from app.schemas.restore import RestoreCreate, RestoreOut
from app.services.audit_service import record_audit

router = APIRouter(prefix="/restore", tags=["restore"])


def _to_out(r: RestoreJob) -> RestoreOut:
    return RestoreOut(
        id=str(r.id),
        target_account_id=str(r.target_account_id),
        scope=r.scope,
        status=r.status,
        dry_run=r.dry_run,
        items_total=r.items_total,
        items_restored=r.items_restored,
        items_failed=r.items_failed,
        bytes_restored=r.bytes_restored,
        started_at=r.started_at,
        finished_at=r.finished_at,
        error_summary=r.error_summary,
        created_at=r.created_at,
    )


@router.get("", response_model=list[RestoreOut])
async def list_jobs(
    db: AsyncSession = Depends(get_db),
    _u: SysUser = Depends(require_permission("restore.view")),
) -> list[RestoreOut]:
    stmt = select(RestoreJob).order_by(RestoreJob.created_at.desc()).limit(200)
    rows = (await db.execute(stmt)).scalars().all()
    return [_to_out(r) for r in rows]


@router.post("", response_model=RestoreOut, status_code=status.HTTP_201_CREATED)
async def create_job(
    payload: RestoreCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("restore.create")),
) -> RestoreOut:
    job = RestoreJob(
        requested_by_user_id=current.id,
        target_account_id=uuid.UUID(payload.target_account_id),
        source_backup_log_id=uuid.UUID(payload.source_backup_log_id)
        if payload.source_backup_log_id
        else None,
        scope=payload.scope.value,
        selection_json=payload.selection,
        destination_kind=payload.destination_kind,
        destination_details_json=payload.destination_details,
        dry_run=payload.dry_run,
        notify_client=payload.notify_client,
        preserve_original_dates=payload.preserve_original_dates,
        apply_restored_label=payload.apply_restored_label,
    )
    db.add(job)
    await db.flush()

    await record_audit(
        db,
        action=AuditAction.RESTORE_TRIGGERED,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        target_table="restore_jobs",
        target_id=str(job.id),
        metadata={"scope": job.scope},
    )
    await db.commit()

    from app.workers.tasks.restore import drive as drive_task, gmail as gmail_task

    if payload.scope in (RestoreScope.DRIVE_TOTAL, RestoreScope.DRIVE_SELECTIVE):
        drive_task.delay(str(job.id))
    elif payload.scope in (RestoreScope.GMAIL_MBOX_BULK, RestoreScope.GMAIL_MESSAGE):
        gmail_task.delay(str(job.id))
    elif payload.scope == RestoreScope.FULL_ACCOUNT:
        drive_task.delay(str(job.id))
        gmail_task.delay(str(job.id))

    await db.refresh(job)
    return _to_out(job)


@router.post("/{job_id}/cancel", response_model=RestoreOut)
async def cancel_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _u: SysUser = Depends(require_permission("restore.cancel")),
) -> RestoreOut:
    job = (await db.execute(select(RestoreJob).where(RestoreJob.id == job_id))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "restore_not_found")
    if job.status not in {RestoreStatus.PENDING.value, RestoreStatus.RUNNING.value}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "cannot_cancel")
    job.status = RestoreStatus.CANCELLED.value
    job.finished_at = datetime.now(timezone.utc)
    await db.commit()
    return _to_out(job)
