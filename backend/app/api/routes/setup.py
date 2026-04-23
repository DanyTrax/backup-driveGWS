"""First-run Setup Wizard endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_client_ip,
    get_current_user,
    get_db,
    get_user_agent,
    require_permission,
)
from app.models.enums import AuditAction
from app.models.users import SysUser
from app.schemas.setup import (
    DirectoryCheckOut,
    NotificationsSetupIn,
    ServiceAccountCheck,
    ServiceAccountUpload,
    SetupState,
    VaultDriveIn,
    VaultDriveOut,
    VaultRootIn,
)
from app.services import setup_service
from app.services.audit_service import record_audit
from app.services.google.directory import check_connection, list_users
from app.services.google.drive import check_shared_drive, ensure_folder

router = APIRouter(prefix="/setup", tags=["setup"])


@router.get("/state", response_model=SetupState)
async def state(
    db: AsyncSession = Depends(get_db),
    _u: SysUser = Depends(get_current_user),
) -> SetupState:
    return SetupState(**await setup_service.load_state(db))


@router.post("/service-account", response_model=ServiceAccountCheck)
async def upload_service_account(
    payload: ServiceAccountUpload,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("settings.edit")),
) -> ServiceAccountCheck:
    try:
        info = await setup_service.store_service_account(
            db, payload.service_account_json, payload.delegated_admin_email
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    await record_audit(
        db,
        action=AuditAction.SETTING_CHANGED,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        target_table="sys_settings",
        target_id="google.service_account_json",
    )
    await db.commit()
    return ServiceAccountCheck(ok=True, **info)


@router.post("/check-directory", response_model=DirectoryCheckOut)
async def check_directory(
    db: AsyncSession = Depends(get_db),
    _u: SysUser = Depends(require_permission("accounts.sync")),
) -> DirectoryCheckOut:
    result = await check_connection(db)
    if result.get("ok"):
        await setup_service.mark_step(db, "delegation_check", True)
        await db.commit()
    return DirectoryCheckOut(
        ok=bool(result.get("ok")),
        users_sample=int(result.get("sample_count", 0)),
        error=result.get("error"),
        detail=result.get("detail"),
    )


@router.post("/vault/shared-drive", response_model=VaultDriveOut)
async def vault_shared_drive(
    payload: VaultDriveIn,
    db: AsyncSession = Depends(get_db),
    _u: SysUser = Depends(require_permission("settings.edit")),
) -> VaultDriveOut:
    check = await check_shared_drive(db, payload.shared_drive_id)
    if not check.get("ok"):
        return VaultDriveOut(ok=False, error=check.get("error"))
    await setup_service.save_shared_drive(db, payload.shared_drive_id)
    await db.commit()
    return VaultDriveOut(ok=True, drive=check.get("drive"))


@router.post(
    "/vault/root-folder",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def vault_root_folder(
    payload: VaultRootIn,
    db: AsyncSession = Depends(get_db),
    _u: SysUser = Depends(require_permission("settings.edit")),
) -> None:
    await setup_service.save_root_folder(db, payload.root_folder_id)
    await db.commit()


@router.post("/vault/create-structure")
async def vault_create_structure(
    db: AsyncSession = Depends(get_db),
    _u: SysUser = Depends(require_permission("settings.edit")),
) -> dict:
    from app.services.settings_service import (
        KEY_VAULT_ROOT_FOLDER_ID,
        KEY_VAULT_SHARED_DRIVE_ID,
        get_value,
    )

    root = await get_value(db, KEY_VAULT_ROOT_FOLDER_ID)
    drive = await get_value(db, KEY_VAULT_SHARED_DRIVE_ID)
    if not root:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "missing_root_folder_id")
    subs = {}
    for name in ("Users", "Platform-Backups", "Reports"):
        child = await ensure_folder(db, name=name, parent_id=root, drive_id=drive)
        subs[name] = child["id"]
    return {"ok": True, "folders": subs}


@router.post(
    "/notifications",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def save_notifications(
    payload: NotificationsSetupIn,
    db: AsyncSession = Depends(get_db),
    _u: SysUser = Depends(require_permission("notifications.manage_global")),
) -> None:
    await setup_service.save_notifications(db, payload.model_dump(exclude_none=True))
    await db.commit()


@router.post(
    "/complete",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def complete(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("settings.edit")),
) -> None:
    await setup_service.mark_completed(db)
    await record_audit(
        db,
        action=AuditAction.SETTING_CHANGED,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        target_table="sys_settings",
        target_id="setup.state",
        message="setup_completed",
    )
    await db.commit()


@router.post("/directory/sync")
async def sync_directory(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("accounts.sync")),
) -> dict:
    """Full sync of Workspace users into gw_accounts."""
    from app.services.accounts_service import sync_workspace_directory

    stats = await sync_workspace_directory(db, triggered_by_user_id=str(current.id))
    await record_audit(
        db,
        action=AuditAction.SETTING_CHANGED,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        target_table="gw_accounts",
        message="directory_sync",
        metadata=stats,
    )
    await db.commit()
    return stats
