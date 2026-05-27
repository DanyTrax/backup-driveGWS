"""Resolución de bóveda por cuenta: unificada, pool alternativo o dedicada."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.vault_pool import VaultPool
from app.services.google.drive import (
    add_service_account_to_shared_drive,
    check_shared_drive,
    create_shared_drive,
    ensure_account_vault,
)
from app.services.settings_service import (
    KEY_VAULT_ROOT_FOLDER_ID,
    KEY_VAULT_SHARED_DRIVE_ID,
    get_value,
)

if TYPE_CHECKING:
    from app.models.accounts import GwAccount

VAULT_MODE_DEFAULT = "default"
VAULT_MODE_POOL = "pool"
VAULT_MODE_DEDICATED = "dedicated"
VAULT_MODES = frozenset({VAULT_MODE_DEFAULT, VAULT_MODE_POOL, VAULT_MODE_DEDICATED})


class VaultAssignmentError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class VaultTarget:
    mode: str
    shared_drive_id: str
    layout_parent_id: str
    label: str


async def resolve_vault_target(db: AsyncSession, account: GwAccount) -> VaultTarget:
    mode = (account.vault_mode or VAULT_MODE_DEFAULT).strip().lower()
    if mode not in VAULT_MODES:
        raise VaultAssignmentError(f"vault_mode_invalid:{mode}")

    if mode == VAULT_MODE_DEDICATED:
        drive_id = (account.dedicated_shared_drive_id or "").strip()
        if not drive_id:
            raise VaultAssignmentError("dedicated_shared_drive_missing")
        return VaultTarget(
            mode=mode,
            shared_drive_id=drive_id,
            layout_parent_id=drive_id,
            label=f"Dedicado ({drive_id[:12]}…)",
        )

    if mode == VAULT_MODE_POOL:
        if account.vault_pool_id is None:
            raise VaultAssignmentError("vault_pool_not_assigned")
        pool = (
            await db.execute(
                select(VaultPool).where(VaultPool.id == account.vault_pool_id)
            )
        ).scalar_one_or_none()
        if pool is None:
            raise VaultAssignmentError("vault_pool_not_found")
        return VaultTarget(
            mode=mode,
            shared_drive_id=pool.shared_drive_id.strip(),
            layout_parent_id=pool.root_folder_id.strip(),
            label=f"Pool: {pool.name}",
        )

    drive_id = (await get_value(db, KEY_VAULT_SHARED_DRIVE_ID) or "").strip()
    root = (await get_value(db, KEY_VAULT_ROOT_FOLDER_ID) or "").strip()
    if not drive_id or not root:
        raise VaultAssignmentError("default_vault_not_configured")
    return VaultTarget(
        mode=VAULT_MODE_DEFAULT,
        shared_drive_id=drive_id,
        layout_parent_id=root,
        label="Vault unificado (por defecto)",
    )


async def resolve_shared_drive_id(db: AsyncSession, account: GwAccount | None) -> str | None:
    if account is None:
        return (await get_value(db, KEY_VAULT_SHARED_DRIVE_ID) or "").strip() or None
    target = await resolve_vault_target(db, account)
    return target.shared_drive_id


async def ensure_dedicated_shared_drive(db: AsyncSession, account: GwAccount) -> str:
    existing = (account.dedicated_shared_drive_id or "").strip()
    if existing:
        chk = await check_shared_drive(db, existing)
        if chk.get("ok"):
            return existing

    safe_email = account.email.replace("@", "_at_").replace(".", "_")[:80]
    name = f"MSA Backup — {safe_email}"
    request_id = f"msa-vault-dedicated-{account.id}"
    created = await create_shared_drive(db, name=name, request_id=request_id)
    drive_id = str(created["id"])
    await add_service_account_to_shared_drive(db, drive_id=drive_id)
    account.dedicated_shared_drive_id = drive_id
    await db.flush()
    return drive_id


async def provision_account_vault(db: AsyncSession, account: GwAccount) -> dict[str, str]:
    """Crea o reutiliza la jerarquía 1-GMAIL/2-DRIVE/3-REPORTS según el modo de bóveda."""
    mode = (account.vault_mode or VAULT_MODE_DEFAULT).strip().lower()
    if mode == VAULT_MODE_DEDICATED:
        await ensure_dedicated_shared_drive(db, account)

    target = await resolve_vault_target(db, account)
    folders = await ensure_account_vault(
        db,
        email=account.email,
        root_folder_id=target.layout_parent_id,
        drive_id=target.shared_drive_id,
        preferred_account_folder_id=(account.drive_vault_folder_id or "").strip() or None,
    )
    account.drive_vault_folder_id = folders.get("root")
    await db.flush()
    return folders


async def apply_vault_assignment(
    db: AsyncSession,
    account: GwAccount,
    *,
    vault_mode: str,
    vault_pool_id: uuid.UUID | None = None,
    reprovision: bool = True,
) -> GwAccount:
    mode = vault_mode.strip().lower()
    if mode not in VAULT_MODES:
        raise VaultAssignmentError(f"vault_mode_invalid:{mode}")

    if mode == VAULT_MODE_POOL:
        if vault_pool_id is None:
            raise VaultAssignmentError("vault_pool_id_required")
        pool = (
            await db.execute(select(VaultPool).where(VaultPool.id == vault_pool_id))
        ).scalar_one_or_none()
        if pool is None:
            raise VaultAssignmentError("vault_pool_not_found")
    elif mode != VAULT_MODE_POOL:
        vault_pool_id = None

    if mode != VAULT_MODE_DEDICATED:
        account.dedicated_shared_drive_id = None

    account.vault_mode = mode
    account.vault_pool_id = vault_pool_id if mode == VAULT_MODE_POOL else None

    if mode == VAULT_MODE_DEDICATED:
        await ensure_dedicated_shared_drive(db, account)

    if reprovision and account.is_backup_enabled:
        await provision_account_vault(db, account)

    await db.flush()
    return account


async def load_account_with_vault_pool(db: AsyncSession, account_id: uuid.UUID) -> GwAccount | None:
    stmt = (
        select(GwAccount)
        .options(selectinload(GwAccount.vault_pool))
        .where(GwAccount.id == account_id)
    )
    return (await db.execute(stmt)).scalar_one_or_none()
