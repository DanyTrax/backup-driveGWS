"""Schemas for platform user CRUD and related admin ops."""
from __future__ import annotations

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.enums import UserStatus

_ROLE_SLUG = re.compile(r"^[a-z][a-z0-9_]{1,31}$")


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=120)
    role_code: str = Field(min_length=2, max_length=32)
    password: str = Field(min_length=12, max_length=256)
    must_change_password: bool = True

    @field_validator("role_code")
    @classmethod
    def _normalize_role(cls, v: str) -> str:
        s = (v or "").strip().lower()
        if not _ROLE_SLUG.match(s):
            raise ValueError("invalid_role_code")
        return s


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    role_code: str | None = None
    status: UserStatus | None = None
    preferred_locale: str | None = Field(default=None, max_length=8)
    preferred_timezone: str | None = Field(default=None, max_length=48)

    @field_validator("role_code")
    @classmethod
    def _normalize_role(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip().lower()
        if not _ROLE_SLUG.match(s):
            raise ValueError("invalid_role_code")
        return s


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
    role_name: str | None = None
    status: str
    mfa_enabled: bool
    last_login_at: datetime | None
    failed_login_count: int
    locked_until: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True
