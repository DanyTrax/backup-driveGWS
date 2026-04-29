"""Schemas para inventario y purga de datos locales de correo."""
from __future__ import annotations

from pydantic import BaseModel, Field


class MailDataInventoryOut(BaseModel):
    account_id: str
    email: str
    maildir_root: str
    maildir_on_disk: bool
    maildir_size_bytes: int | None = None
    gyb_work_path: str
    gyb_work_has_content: bool
    gyb_work_size_bytes: int | None = None
    gmail_backup_logs_count: int
    webmail_tokens_count: int
    imap_enabled: bool
    imap_password_configured: bool


class AccountMailPurgeIn(BaseModel):
    confirmation_email: str = Field(..., min_length=3, description="Debe coincidir exactamente con el correo de la cuenta.")
    maildir: bool = False
    gyb_workdir: bool = False
    gmail_backup_logs: bool = False
    webmail_tokens: bool = False
    revoke_imap_credentials: bool = False


class AccountMailPurgeOut(BaseModel):
    maildir_cleared: int = 0
    gyb_workdir_cleared: int = 0
    gmail_logs_deleted: int = 0
    webmail_tokens_deleted: int = 0
    imap_credentials_revoked: bool = False


class PurgeAllLocalMailIn(BaseModel):
    confirmation: str = Field(..., min_length=8)


class PurgeAllLocalMailOut(BaseModel):
    workspace_accounts: int
    maildirs_cleared: int
    gyb_workdirs_cleared: int
    gmail_backup_logs_deleted: int
    webmail_tokens_deleted: int
