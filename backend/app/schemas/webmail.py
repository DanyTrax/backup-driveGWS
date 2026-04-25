"""Schemas for webmail SSO and magic links."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class MagicLinkIn(BaseModel):
    purpose: str = Field(pattern="^(first_setup|password_reset|client_sso)$")
    ttl_minutes: int = Field(default=60, ge=5, le=1440)


class MagicLinkOut(BaseModel):
    url: str
    expires_at: datetime


class SetWebmailPasswordIn(BaseModel):
    new_password: str = Field(min_length=10, max_length=128)


class AdminSsoOut(BaseModel):
    url: str
    expires_at: datetime


class PasswordAssignLinkIn(BaseModel):
    """Vigencia del enlace de asignación; máximo 24 h."""
    ttl_hours: int = Field(default=24, ge=1, le=24)


class PasswordAssignLinkOut(BaseModel):
    url: str
    expires_at: datetime
    ttl_minutes: int


class PasswordSetupStatusOut(BaseModel):
    email: str
    expires_at: datetime


class PasswordSetupCompleteIn(BaseModel):
    token: str = Field(min_length=8, max_length=2000)
    new_password: str = Field(min_length=10, max_length=128)
