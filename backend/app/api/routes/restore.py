"""Restore job endpoints (Drive / Gmail)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_client_ip,
    get_db,
    get_user_agent,
    require_permission,
)
from app.models.accounts import GwAccount
from app.models.enums import AuditAction, RestoreScope, RestoreStatus
from app.models.restore import RestoreJob
from app.models.users import SysUser
from app.schemas.restore import (
    RestoreBulkDeleteIn,
    RestoreBulkDeleteOut,
    RestoreCreate,
    RestoreOut,
)
from app.services.audit_service import record_audit
from app.workers.celery_app import celery_app

router = APIRouter(prefix="/restore", tags=["restore"])


def _to_out(r: RestoreJob, account_email: str | None = None) -> RestoreOut:
    return RestoreOut(
        id=str(r.id),
        target_account_id=str(r.target_account_id),
        account_email=account_email,
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


async def _email_for_account(db: AsyncSession, account_id: uuid.UUID) -> str | None:
    return (
        await db.execute(select(GwAccount.email).where(GwAccount.id == account_id))
    ).scalar_one_or_none()


@router.get("", response_model=list[RestoreOut])
async def list_jobs(
    status_filter: str | None = None,
    scope_filter: str | None = None,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    _u: SysUser = Depends(require_permission("restore.view")),
) -> list[RestoreOut]:
    lim = max(1, min(int(limit), 500))
    stmt = (
        select(RestoreJob, GwAccount.email)
        .join(GwAccount, RestoreJob.target_account_id == GwAccount.id)
        .order_by(RestoreJob.created_at.desc())
        .limit(lim)
    )
    if status_filter:
        allowed_s = {s.value for s in RestoreStatus}
        if status_filter not in allowed_s:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="invalid_status")
        stmt = stmt.where(RestoreJob.status == status_filter)
    if scope_filter:
        allowed_sc = {s.value for s in RestoreScope}
        if scope_filter not in allowed_sc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="invalid_scope")
        stmt = stmt.where(RestoreJob.scope == scope_filter)
    rows = (await db.execute(stmt)).all()
    return [_to_out(r, account_email=email) for r, email in rows]


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
    email = await _email_for_account(db, job.target_account_id)
    return _to_out(job, account_email=email)


@router.post("/bulk-delete", response_model=RestoreBulkDeleteOut)
async def bulk_delete_restores(
    payload: RestoreBulkDeleteIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("restore.delete")),
) -> RestoreBulkDeleteOut:
    wanted = [x.strip() for x in payload.ids if x and str(x).strip()]
    if not wanted:
        return RestoreBulkDeleteOut(deleted=0, skipped_running=[], not_found=[])

    uuids: list[uuid.UUID] = []
    not_found: list[str] = []
    for s in wanted:
        try:
            uuids.append(uuid.UUID(s))
        except ValueError:
            not_found.append(s)

    rows = list(
        (await db.execute(select(RestoreJob).where(RestoreJob.id.in_(uuids)))).scalars().all()
    )
    found_ids = {r.id for r in rows}
    for uid in uuids:
        if uid not in found_ids:
            not_found.append(str(uid))

    skipped_running: list[str] = []
    to_delete: list[RestoreJob] = []
    for r in rows:
        if r.status == RestoreStatus.RUNNING.value:
            skipped_running.append(str(r.id))
        else:
            to_delete.append(r)

    for r in to_delete:
        cid = (r.celery_task_id or "").strip()
        if cid:
            AsyncResult(cid, app=celery_app).revoke(terminate=True)

    ids_del = [r.id for r in to_delete]
    if ids_del:
        await db.execute(delete(RestoreJob).where(RestoreJob.id.in_(ids_del)))

    ip = get_client_ip(request)
    ua = get_user_agent(request)
    for r in to_delete:
        await record_audit(
            db,
            action=AuditAction.RESTORE_JOB_DELETED,
            actor_user_id=current.id,
            actor_label=current.email,
            ip_address=ip,
            user_agent=ua,
            target_table="restore_jobs",
            target_id=str(r.id),
        )

    await db.commit()
    return RestoreBulkDeleteOut(
        deleted=len(ids_del),
        skipped_running=skipped_running,
        not_found=not_found,
    )


@router.delete(
    "/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def delete_job(
    job_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("restore.delete")),
) -> None:
    job = (await db.execute(select(RestoreJob).where(RestoreJob.id == job_id))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="restore_not_found")
    if job.status == RestoreStatus.RUNNING.value:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"error": "restore_running"},
        )
    cid = (job.celery_task_id or "").strip()
    if cid:
        AsyncResult(cid, app=celery_app).revoke(terminate=True)
    await db.execute(delete(RestoreJob).where(RestoreJob.id == job_id))
    await record_audit(
        db,
        action=AuditAction.RESTORE_JOB_DELETED,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        target_table="restore_jobs",
        target_id=str(job_id),
    )
    await db.commit()


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
    await db.refresh(job)
    email = await _email_for_account(db, job.target_account_id)
    return _to_out(job, account_email=email)
