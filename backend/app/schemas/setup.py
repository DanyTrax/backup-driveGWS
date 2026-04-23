"""Setup wizard schemas."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, EmailStr, Field


class SetupState(BaseModel):
    completed: bool
    current_step: str
    steps: dict[str, bool]
    google_client_id: str | None = None
    required_scopes: list[str] = []


class ServiceAccountUpload(BaseModel):
    service_account_json: str = Field(min_length=10)
    delegated_admin_email: EmailStr


class ServiceAccountCheck(BaseModel):
    ok: bool
    client_id: str | None = None
    client_email: str | None = None
    required_scopes: list[str]


class DirectoryCheckOut(BaseModel):
    ok: bool
    users_sample: int = 0
    error: str | None = None
    detail: str | None = None


class VaultDriveIn(BaseModel):
    shared_drive_id: str = Field(min_length=4)


class VaultDriveOut(BaseModel):
    ok: bool
    drive: dict[str, Any] | None = None
    error: str | None = None


class VaultRootIn(BaseModel):
    root_folder_id: str = Field(min_length=4)


class NotificationsSetupIn(BaseModel):
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    discord_webhook_url: str | None = None
    gmail_from: EmailStr | None = None
    gmail_delegated_subject: EmailStr | None = None
    gmail_recipients: list[EmailStr] | None = None


class FirstAdminDetected(BaseModel):
    exists: bool
    email: str | None = None
