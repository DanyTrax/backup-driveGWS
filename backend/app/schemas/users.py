"""Schemas for platform user CRUD and related admin ops."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import UserRole, UserStatus


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=120)
    role_code: UserRole
    password: str = Field(min_length=12, max_length=256)
    must_change_password: bool = True


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    role_code: UserRole | None = None
    status: UserStatus | None = None
    preferred_locale: str | None = Field(default=None, max_length=8)
    preferred_timezone: str | None = Field(default=None, max_length=48)


class AdminPasswordReset(BaseModel):
    new_password: str = Field(min_length=12, max_length=256)
    must_change_password: bool = True


class MailboxDelegationsPut(BaseModel):
    account_ids: list[uuid.UUID] = Field(default_factory=list, max_length=2048)


class UserOut(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    role_code: str
    status: str
    mfa_enabled: bool
    last_login_at: datetime | None
    failed_login_count: int
    locked_until: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True
