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
