"""Pydantic schemas for authentication flows."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    mfa_code: str | None = Field(default=None, min_length=6, max_length=12)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    mfa_required: bool = False
    mfa_challenge: str | None = None


class MfaChallenge(BaseModel):
    """Returned on first auth step when MFA is enabled."""

    mfa_required: bool = True
    mfa_challenge: str
    user_id: str


class RefreshRequest(BaseModel):
    refresh_token: str


class MfaEnrollStart(BaseModel):
    otpauth_uri: str
    secret: str
    qr_png_base64: str


class MfaEnrollConfirm(BaseModel):
    code: str = Field(min_length=6, max_length=12)


class MfaEnrollResult(BaseModel):
    backup_codes: list[str]


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=12, max_length=256)


class PasswordResetRequestIn(BaseModel):
    email: EmailStr


class PasswordResetConfirmIn(BaseModel):
    token: str = Field(min_length=16)
    new_password: str = Field(min_length=12, max_length=256)


class ProfileOut(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    role_code: str
    role_name: str | None = None
    mfa_enabled: bool
    must_change_password: bool
    status: str
    last_login_at: datetime | None = None
    preferred_locale: str
    preferred_timezone: str
    permissions: list[str]
    mailbox_delegated_account_ids: list[str] = Field(default_factory=list)
