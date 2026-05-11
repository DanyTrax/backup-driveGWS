"""API: materializar ZIPs del vault Gmail en el servidor (Fase 5)."""
from __future__ import annotations

import uuid
from pathlib import Path

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    assert_vault_drive_account_access,
    get_db,
    get_user_permissions,
    require_any_permission,
)
from app.core.config import get_settings
from app.models.accounts import GwAccount
from app.models.gmail_vault import GmailVaultMaterialization
from app.models.tasks import BackupTask
from app.models.users import SysUser
from app.models.vault_drive_delegation import SysUserVaultDriveDelegation
from app.schemas.gmail_vault_materialize import (
    GmailVaultMaterializeCreateIn,
    GmailVaultMaterializeListItem,
    GmailVaultMaterializeOut,
    materialization_to_out,
)
from app.services.gmail_vault_materialize_logic import (
    GmailVaultMaterializeError,
    resolve_materialize_window,
)
from app.services.gmail_vault_materialize_service import (
    create_materialization_session,
    expire_session_if_ttl_elapsed,
    materialization_paths,
    purge_materialization_local,
)
from app.services.progress_bus import last_event
from app.workers.celery_app import celery_app
from app.workers.tasks.gmail_vault_materialize import run as materialize_celery_run

router = APIRouter()


@router.post(
    "/materialize",
    response_model=GmailVaultMaterializeOut,
    status_code=status.HTTP_201_CREATED,
    summary="Encolar descarga de ZIPs del vault Gmail al servidor",
)
async def gmail_vault_materialize_create(
    payload: GmailVaultMaterializeCreateIn,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(
        require_any_permission("vault_drive.view_all", "vault_drive.view_delegated")
    ),
) -> GmailVaultMaterializeOut:
    await assert_vault_drive_account_access(db, current, payload.account_id)
    try:
        w0, w1 = resolve_materialize_window(
            payload.mode,
            anchor_date=payload.anchor_date,
            date_from=payload.date_from,
            date_to=payload.date_to,
            calendar_month=payload.calendar_month,
        )
    except GmailVaultMaterializeError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    s = get_settings()
    ttl = payload.ttl_days if payload.ttl_days is not None else s.gmail_vault_materialize_ttl_days_default
    ttl = min(int(ttl), int(s.gmail_vault_materialize_ttl_days_max))

    try:
        row = await create_materialization_session(
            db,
            account_id=payload.account_id,
            task_id=payload.task_id,
            requested_mode=payload.mode,
            window_start=w0,
            window_end=w1,
            ttl_days=ttl,
            created_by_user_id=current.id,
        )
    except GmailVaultMaterializeError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    expected = materialization_paths(payload.account_id, row.id)
    if Path(row.path_local).resolve() != expected:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="path_local_mismatch")

    materialize_celery_run.delay(str(row.id))
    refreshed = (
        await db.execute(select(GmailVaultMaterialization).where(GmailVaultMaterialization.id == row.id))
    ).scalar_one()
    return materialization_to_out(refreshed)


@router.get(
    "/materialize/recent",
    response_model=list[GmailVaultMaterializeListItem],
    summary="Historial reciente de materializaciones (vault ZIP → servidor)",
)
async def gmail_vault_materialize_recent(
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(
        require_any_permission("vault_drive.view_all", "vault_drive.view_delegated")
    ),
) -> list[GmailVaultMaterializeListItem]:
    perms = get_user_permissions(current)
    lim = max(1, min(int(limit), 200))
    stmt = (
        select(GmailVaultMaterialization, GwAccount.email, BackupTask.name)
        .join(GwAccount, GmailVaultMaterialization.account_id == GwAccount.id)
        .outerjoin(BackupTask, GmailVaultMaterialization.task_id == BackupTask.id)
        .order_by(GmailVaultMaterialization.created_at.desc())
        .limit(lim)
    )
    if "vault_drive.view_all" not in perms:
        deleg = select(SysUserVaultDriveDelegation.gw_account_id).where(
            SysUserVaultDriveDelegation.sys_user_id == current.id
        )
        stmt = stmt.where(GmailVaultMaterialization.account_id.in_(deleg))
    rows = (await db.execute(stmt)).all()
    out: list[GmailVaultMaterializeListItem] = []
    for m, email, tname in rows:
        out.append(
            GmailVaultMaterializeListItem(
                id=str(m.id),
                account_id=str(m.account_id),
                account_email=email,
                task_id=str(m.task_id) if m.task_id else None,
                task_name=tname,
                requested_mode=m.requested_mode,
                date_from=m.date_from,
                date_to=m.date_to,
                status=m.status,
                created_at=m.created_at,
                updated_at=m.updated_at,
                ttl_expires_at=m.ttl_expires_at,
                error_summary=m.error_summary,
                progress_json=dict(m.progress_json or {}),
            )
        )
    return out


@router.get(
    "/materialize/{session_id}",
    response_model=GmailVaultMaterializeOut,
    summary="Estado y progreso de una sesión de materialización",
)
async def gmail_vault_materialize_get(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(
        require_any_permission("vault_drive.view_all", "vault_drive.view_delegated")
    ),
) -> GmailVaultMaterializeOut:
    row = (
        await db.execute(select(GmailVaultMaterialization).where(GmailVaultMaterialization.id == session_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="session_not_found")
    await assert_vault_drive_account_access(db, current, row.account_id)
    if await expire_session_if_ttl_elapsed(db, row):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="session_expired")
    refreshed = (
        await db.execute(
            select(GmailVaultMaterialization, GwAccount.email)
            .join(GwAccount, GmailVaultMaterialization.account_id == GwAccount.id)
            .where(GmailVaultMaterialization.id == session_id)
        )
    ).one_or_none()
    if refreshed is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="session_not_found")
    row_mat, acc_email = refreshed
    base = materialization_to_out(row_mat)
    snap = await last_event(str(session_id))
    return base.model_copy(update={"live_progress": snap, "account_email": acc_email})


@router.delete(
    "/materialize/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Cancelar y borrar materialización local",
)
async def gmail_vault_materialize_delete(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(
        require_any_permission("vault_drive.view_all", "vault_drive.view_delegated")
    ),
) -> None:
    row = (
        await db.execute(select(GmailVaultMaterialization).where(GmailVaultMaterialization.id == session_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="session_not_found")
    await assert_vault_drive_account_access(db, current, row.account_id)

    cid = (row.progress_json or {}).get("celery_task_id")
    if isinstance(cid, str) and cid.strip():
        AsyncResult(cid.strip(), app=celery_app).revoke(terminate=True)

    await purge_materialization_local(row)
    await db.delete(row)
    await db.commit()
