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
    require_any_permission,
)
from app.core.config import get_settings
from app.models.gmail_vault import GmailVaultMaterialization
from app.models.users import SysUser
from app.schemas.gmail_vault_materialize import (
    GmailVaultMaterializeCreateIn,
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
        await db.execute(select(GmailVaultMaterialization).where(GmailVaultMaterialization.id == session_id))
    ).scalar_one_or_none()
    if refreshed is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="session_not_found")
    return materialization_to_out(refreshed)


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
