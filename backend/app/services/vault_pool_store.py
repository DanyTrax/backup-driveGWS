"""CRUD de pools de bóveda (Shared Drives adicionales)."""
from __future__ import annotations

import uuid

from googleapiclient.errors import HttpError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accounts import GwAccount
from app.models.vault_pool import VaultPool
from app.services.google.drive import (
    add_service_account_to_shared_drive,
    check_shared_drive,
    create_shared_drive,
    ensure_folder,
)

DEFAULT_POOL_ROOT_FOLDER_NAME = "BackupRoot"


async def list_pools(db: AsyncSession) -> list[tuple[VaultPool, int]]:
    stmt = (
        select(VaultPool, func.count(GwAccount.id))
        .outerjoin(GwAccount, GwAccount.vault_pool_id == VaultPool.id)
        .group_by(VaultPool.id)
        .order_by(VaultPool.name.asc())
    )
    rows = (await db.execute(stmt)).all()
    return [(pool, int(cnt or 0)) for pool, cnt in rows]


async def get_pool(db: AsyncSession, pool_id: uuid.UUID) -> VaultPool | None:
    return (
        await db.execute(select(VaultPool).where(VaultPool.id == pool_id))
    ).scalar_one_or_none()


async def _assert_unique_pool_name(db: AsyncSession, name: str, *, exclude_id: uuid.UUID | None = None) -> None:
    nm = name.strip()
    stmt = select(VaultPool).where(VaultPool.name == nm)
    if exclude_id is not None:
        stmt = stmt.where(VaultPool.id != exclude_id)
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        raise ValueError("duplicate_name")


async def provision_pool_in_google(
    db: AsyncSession,
    *,
    name: str,
    description: str | None = None,
    root_folder_name: str = DEFAULT_POOL_ROOT_FOLDER_NAME,
    drive_display_name: str | None = None,
) -> VaultPool:
    """Crea Shared Drive + permiso SA + carpeta raíz y registra el pool en BD."""
    await _assert_unique_pool_name(db, name)

    panel_name = name.strip()
    drive_name = (drive_display_name or f"MSA Backup — {panel_name}").strip()[:250]
    root_name = (root_folder_name or DEFAULT_POOL_ROOT_FOLDER_NAME).strip() or DEFAULT_POOL_ROOT_FOLDER_NAME
    request_id = f"msa-vault-pool-{uuid.uuid4()}"

    try:
        created = await create_shared_drive(db, name=drive_name, request_id=request_id)
    except HttpError as exc:
        raise ValueError(f"google_shared_drive_create_failed:http_{exc.resp.status}") from exc

    drive_id = str(created["id"])
    await add_service_account_to_shared_drive(db, drive_id=drive_id)
    root_folder = await ensure_folder(
        db,
        name=root_name,
        parent_id=drive_id,
        drive_id=drive_id,
    )
    root_id = str(root_folder["id"])

    chk = await check_shared_drive(db, drive_id)
    if not chk.get("ok"):
        raise ValueError("shared_drive_not_accessible_after_create")

    row = VaultPool(
        name=panel_name,
        shared_drive_id=drive_id,
        root_folder_id=root_id,
        description=(description or "").strip() or None,
    )
    db.add(row)
    await db.flush()
    return row


async def create_pool(
    db: AsyncSession,
    *,
    name: str,
    shared_drive_id: str,
    root_folder_id: str,
    description: str | None,
) -> VaultPool:
    chk = await check_shared_drive(db, shared_drive_id.strip())
    if not chk.get("ok"):
        raise ValueError("shared_drive_not_accessible")

    await _assert_unique_pool_name(db, name)

    row = VaultPool(
        name=name.strip(),
        shared_drive_id=shared_drive_id.strip(),
        root_folder_id=root_folder_id.strip(),
        description=(description or "").strip() or None,
    )
    db.add(row)
    await db.flush()
    return row


async def update_pool(
    db: AsyncSession,
    pool: VaultPool,
    *,
    name: str | None = None,
    shared_drive_id: str | None = None,
    root_folder_id: str | None = None,
    description: str | None = None,
) -> VaultPool:
    if name is not None:
        nm = name.strip()
        dup = (
            await db.execute(
                select(VaultPool).where(VaultPool.name == nm, VaultPool.id != pool.id)
            )
        ).scalar_one_or_none()
        if dup:
            raise ValueError("duplicate_name")
        pool.name = nm
    if shared_drive_id is not None:
        sid = shared_drive_id.strip()
        chk = await check_shared_drive(db, sid)
        if not chk.get("ok"):
            raise ValueError("shared_drive_not_accessible")
        pool.shared_drive_id = sid
    if root_folder_id is not None:
        pool.root_folder_id = root_folder_id.strip()
    if description is not None:
        pool.description = description.strip() or None
    await db.flush()
    return pool


async def delete_pool(db: AsyncSession, pool_id: uuid.UUID) -> bool:
    pool = await get_pool(db, pool_id)
    if pool is None:
        return False
    in_use = int(
        (
            await db.execute(
                select(func.count()).select_from(GwAccount).where(GwAccount.vault_pool_id == pool_id)
            )
        ).scalar_one()
    )
    if in_use:
        raise ValueError("pool_in_use")
    await db.delete(pool)
    return True
