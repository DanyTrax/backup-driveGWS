"""Schemas for gw_accounts."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr


class AccountOut(BaseModel):
    id: str
    email: EmailStr
    full_name: str | None
    org_unit_path: str | None
    is_workspace_admin: bool
    workspace_status: str
    is_backup_enabled: bool
    backup_enabled_at: datetime | None
    imap_enabled: bool
    drive_vault_folder_id: str | None
    last_sync_at: datetime | None
    last_successful_backup_at: datetime | None
    total_bytes_cache: int | None
    total_messages_cache: int | None
    # Bandeja en volumen (Dovecot); False si no existe cur/new/tmp o está vaciada hasta próximo Gmail backup.
    maildir_on_disk: bool
    maildir_user_cleared_at: datetime | None


class AccountApproveIn(BaseModel):
    exclusion_reason: str | None = None


class AccountRevokeIn(BaseModel):
    reason: str | None = None


class SyncOut(BaseModel):
    ok: bool
    accounts_total: int
    accounts_new: int
    accounts_updated: int
    accounts_suspended: int
    accounts_deleted: int
    started_at: str
    finished_at: str


class AccountAccessCheckOut(BaseModel):
    """Resultado de GET /accounts/{id}/verify-access (rclone + GYB + Maildir en disco)."""

    account_id: str
    email: EmailStr
    drive_ok: bool
    drive_detail: str | None
    gmail_ok: bool
    gmail_detail: str | None
    maildir_path: str | None
    maildir_layout_ok: bool
