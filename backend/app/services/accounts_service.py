"""Workspace account synchronization and opt-in management."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accounts import GwAccount, GwSyncLog
from app.models.enums import AccountStatus
from app.services.google.directory import WorkspaceUser, list_users


def _status_for(u: WorkspaceUser) -> str:
    if u.archived or u.suspended:
        return AccountStatus.SUSPENDED_IN_WORKSPACE.value
    return AccountStatus.DISCOVERED.value


async def sync_workspace_directory(
    db: AsyncSession, *, triggered_by_user_id: str | None = None
) -> dict[str, Any]:
    """Reconcile `gw_accounts` with the Workspace directory.

    - Inserts new users as DISCOVERED (is_backup_enabled=False).
    - Updates names, status and org unit for existing users.
    - Marks users missing from the directory as DELETED_IN_WORKSPACE.
    """
    started = datetime.now(timezone.utc)
    try:
        remote_users = await list_users(db)
    except Exception as exc:
        sync = GwSyncLog(
            started_at=started,
            finished_at=datetime.now(timezone.utc),
            triggered_by_user_id=uuid.UUID(triggered_by_user_id) if triggered_by_user_id else None,
            ok=False,
            error_message=str(exc),
        )
        db.add(sync)
        await db.flush()
        raise

    by_email: dict[str, WorkspaceUser] = {u.primary_email: u for u in remote_users}

    existing = (await db.execute(select(GwAccount))).scalars().all()
    existing_by_email = {a.email: a for a in existing}

    new_count = 0
    updated_count = 0
    suspended_count = 0

    now = datetime.now(timezone.utc)
    for email, u in by_email.items():
        acc = existing_by_email.get(email)
        new_status = _status_for(u)
        if acc is None:
            acc = GwAccount(
                email=email,
                google_user_id=u.id or None,
                full_name=u.full_name,
                given_name=u.given_name,
                family_name=u.family_name,
                org_unit_path=u.org_unit_path,
                is_workspace_admin=u.is_admin,
                workspace_status=new_status,
                discovered_at=now,
            )
            db.add(acc)
            new_count += 1
        else:
            changed = False
            for field, value in (
                ("google_user_id", u.id or None),
                ("full_name", u.full_name),
                ("given_name", u.given_name),
                ("family_name", u.family_name),
                ("org_unit_path", u.org_unit_path),
                ("is_workspace_admin", u.is_admin),
                ("workspace_status", new_status),
            ):
                if getattr(acc, field) != value:
                    setattr(acc, field, value)
                    changed = True
            if changed:
                updated_count += 1
        if new_status == AccountStatus.SUSPENDED_IN_WORKSPACE.value:
            suspended_count += 1

    deleted_count = 0
    for email, acc in existing_by_email.items():
        if email not in by_email and acc.workspace_status != AccountStatus.DELETED_IN_WORKSPACE.value:
            acc.workspace_status = AccountStatus.DELETED_IN_WORKSPACE.value
            deleted_count += 1

    finished = datetime.now(timezone.utc)
    log_row = GwSyncLog(
        started_at=started,
        finished_at=finished,
        triggered_by_user_id=uuid.UUID(triggered_by_user_id) if triggered_by_user_id else None,
        ok=True,
        accounts_total=len(by_email),
        accounts_new=new_count,
        accounts_updated=updated_count,
        accounts_suspended=suspended_count,
        accounts_deleted=deleted_count,
    )
    db.add(log_row)
    await db.flush()

    return {
        "ok": True,
        "accounts_total": len(by_email),
        "accounts_new": new_count,
        "accounts_updated": updated_count,
        "accounts_suspended": suspended_count,
        "accounts_deleted": deleted_count,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
    }


async def approve_account(
    db: AsyncSession,
    account: GwAccount,
    *,
    approved_by_user_id: str,
) -> None:
    """Enable backup for an account and provision its vault folders lazily."""
    from app.services.google.drive import ensure_account_vault
    from app.services.settings_service import (
        KEY_VAULT_ROOT_FOLDER_ID,
        KEY_VAULT_SHARED_DRIVE_ID,
        get_value,
    )

    if account.workspace_status == AccountStatus.DELETED_IN_WORKSPACE.value:
        raise ValueError("account_deleted_in_workspace")

    root = await get_value(db, KEY_VAULT_ROOT_FOLDER_ID)
    if not root:
        raise ValueError("vault_root_folder_not_configured")
    drive_id = await get_value(db, KEY_VAULT_SHARED_DRIVE_ID)

    folders = await ensure_account_vault(
        db, email=account.email, root_folder_id=root, drive_id=drive_id
    )
    account.drive_vault_folder_id = folders.get("root")
    account.is_backup_enabled = True
    account.backup_enabled_at = datetime.now(timezone.utc)
    account.backup_enabled_by = uuid.UUID(approved_by_user_id)

    from pathlib import Path

    account.maildir_path = f"/var/mail/msa/{account.email}"
    await db.flush()


async def revoke_account(db: AsyncSession, account: GwAccount) -> None:
    account.is_backup_enabled = False
    account.imap_enabled = False
    await db.flush()
