"""Explorador de la bóveda de respaldo en Google Drive por cuenta Workspace."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_db,
    get_user_permissions,
    require_any_permission,
    vault_drive_reader_for_account,
)
from app.models.accounts import GwAccount
from app.models.users import SysUser
from app.models.vault_drive_delegation import SysUserVaultDriveDelegation
from app.schemas.vault_drive_browser import (
    VaultDriveAccountOut,
    VaultDriveChildrenPageOut,
    VaultDriveItemOut,
    VaultDriveSearchOut,
)
from app.services.vault_drive_browser_service import list_vault_page, search_vault_subtree

router = APIRouter()


@router.get(
    "/vault-drive/accounts",
    response_model=list[VaultDriveAccountOut],
    summary="Cuentas cuya bóveda en Drive puede explorar el usuario actual",
)
async def vault_drive_list_accounts(
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(
        require_any_permission("vault_drive.view_all", "vault_drive.view_delegated")
    ),
) -> list[VaultDriveAccountOut]:
    perms = get_user_permissions(current)
    stmt = select(GwAccount).where(GwAccount.drive_vault_folder_id.isnot(None)).order_by(
        GwAccount.email.asc()
    )
    stmt = stmt.where(GwAccount.drive_vault_folder_id != "")
    if "vault_drive.view_delegated" in perms and "vault_drive.view_all" not in perms:
        stmt = stmt.where(
            GwAccount.id.in_(
                select(SysUserVaultDriveDelegation.gw_account_id).where(
                    SysUserVaultDriveDelegation.sys_user_id == current.id
                )
            )
        )
    rows = (await db.execute(stmt)).scalars().all()
    return [VaultDriveAccountOut(id=str(a.id), email=a.email) for a in rows]


@router.get(
    "/{account_id}/vault-drive/children",
    response_model=VaultDriveChildrenPageOut,
    summary="Hijos de una carpeta dentro de la bóveda de la cuenta (paginado)",
)
async def vault_drive_children(
    account_id: uuid.UUID,
    parent_id: str | None = Query(
        default=None,
        description="Id de carpeta en Drive; omitir para usar la raíz de la bóveda de la cuenta",
    ),
    page_token: str | None = Query(default=None),
    page_size: int = Query(default=50, ge=10, le=200),
    _viewer: SysUser = Depends(vault_drive_reader_for_account),
    db: AsyncSession = Depends(get_db),
) -> VaultDriveChildrenPageOut:
    acc = (
        await db.execute(select(GwAccount).where(GwAccount.id == account_id))
    ).scalar_one_or_none()
    if acc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account_not_found")
    vault_root = (acc.drive_vault_folder_id or "").strip()
    if not vault_root:
        raise HTTPException(status.HTTP_409_CONFLICT, "missing_drive_vault_folder_id")

    data = await list_vault_page(
        db,
        vault_root_id=vault_root,
        parent_folder_id=parent_id,
        page_token=page_token,
        page_size=page_size,
    )
    if data.get("error") == "parent_not_in_vault":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={"error": "vault_parent_forbidden"},
        )
    if data.get("error"):
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail={"error": data["error"]},
        )
    return VaultDriveChildrenPageOut(
        items=[VaultDriveItemOut(**i) for i in data["items"]],
        next_page_token=data.get("next_page_token"),
    )


@router.get(
    "/{account_id}/vault-drive/search",
    response_model=VaultDriveSearchOut,
    summary="Búsqueda por nombre en el árbol bajo la raíz vault (acotada)",
)
async def vault_drive_search(
    account_id: uuid.UUID,
    q: str = Query(min_length=2, max_length=200),
    _viewer: SysUser = Depends(vault_drive_reader_for_account),
    db: AsyncSession = Depends(get_db),
) -> VaultDriveSearchOut:
    acc = (
        await db.execute(select(GwAccount).where(GwAccount.id == account_id))
    ).scalar_one_or_none()
    if acc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account_not_found")
    vault_root = (acc.drive_vault_folder_id or "").strip()
    if not vault_root:
        raise HTTPException(status.HTTP_409_CONFLICT, "missing_drive_vault_folder_id")
    data = await search_vault_subtree(db, vault_root_id=vault_root, name_substring=q)
    err = data.get("error")
    if err == "query_too_short":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"error": err})
    if err == "invalid_query":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"error": err})
    if err:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail={"error": err})
    return VaultDriveSearchOut(
        items=[VaultDriveItemOut(**i) for i in data["items"]],
        truncated=bool(data.get("truncated")),
    )
