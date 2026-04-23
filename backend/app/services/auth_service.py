"""Authentication orchestration: login, MFA, refresh, lockout, sessions."""
from __future__ import annotations

import base64
import io
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.crypto import decrypt_str, encrypt_str
from app.core.security import (
    compute_lockout_seconds,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_backup_codes,
    generate_totp_secret,
    hash_password,
    hash_token,
    totp_provisioning_uri,
    verify_password,
    verify_totp,
)
from app.models.enums import AuditAction, UserRole, UserStatus
from app.models.users import SysSession, SysUser
from app.services.audit_service import record_audit

settings = get_settings()


class AuthError(Exception):
    """Base class for authentication failures."""


class InvalidCredentials(AuthError):
    pass


class AccountLocked(AuthError):
    def __init__(self, retry_after_seconds: int):
        super().__init__("account_locked")
        self.retry_after_seconds = retry_after_seconds


class AccountSuspended(AuthError):
    pass


class MfaRequired(AuthError):
    def __init__(self, user_id: str):
        super().__init__("mfa_required")
        self.user_id = user_id


class InvalidMfaCode(AuthError):
    pass


@dataclass(slots=True)
class IssuedTokens:
    access_token: str
    refresh_token: str
    expires_in: int
    user: SysUser


async def _load_user_by_email(db: AsyncSession, email: str) -> SysUser | None:
    stmt = select(SysUser).where(SysUser.email == email.lower().strip())
    return (await db.execute(stmt)).scalar_one_or_none()


async def _load_user_by_id(db: AsyncSession, user_id: str | uuid.UUID) -> SysUser | None:
    uid = uuid.UUID(str(user_id)) if not isinstance(user_id, uuid.UUID) else user_id
    stmt = select(SysUser).where(SysUser.id == uid)
    return (await db.execute(stmt)).scalar_one_or_none()


def _is_locked(user: SysUser, now: datetime) -> int:
    if user.locked_until is None:
        return 0
    if user.locked_until > now:
        return int((user.locked_until - now).total_seconds())
    return 0


async def _register_failed_login(db: AsyncSession, user: SysUser) -> None:
    user.failed_login_count = (user.failed_login_count or 0) + 1
    seconds = compute_lockout_seconds(user.failed_login_count)
    if seconds > 0:
        user.locked_until = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    await db.flush()


async def _reset_failed_counter(db: AsyncSession, user: SysUser, ip: str | None) -> None:
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = datetime.now(timezone.utc)
    user.last_login_ip = ip
    await db.flush()


async def _issue_session_tokens(
    db: AsyncSession,
    user: SysUser,
    user_agent: str | None,
    ip: str | None,
) -> IssuedTokens:
    access_token, _, access_exp = create_access_token(str(user.id), user.role_code)
    refresh_token, refresh_jti, refresh_exp = create_refresh_token(str(user.id), user.role_code)

    session = SysSession(
        user_id=user.id,
        jti=refresh_jti,
        refresh_token_hash=hash_token(refresh_token),
        user_agent=(user_agent or "")[:400] or None,
        ip_address=ip,
        expires_at=refresh_exp,
        last_used_at=datetime.now(timezone.utc),
    )
    db.add(session)
    await db.flush()

    expires_in = int((access_exp - datetime.now(timezone.utc)).total_seconds())
    return IssuedTokens(access_token, refresh_token, expires_in, user)


async def authenticate(
    db: AsyncSession,
    email: str,
    password: str,
    mfa_code: str | None,
    *,
    ip: str | None,
    user_agent: str | None,
) -> IssuedTokens:
    user = await _load_user_by_email(db, email)
    now = datetime.now(timezone.utc)

    if user is None:
        await record_audit(
            db,
            action=AuditAction.LOGIN_FAILED,
            actor_label=email,
            ip_address=ip,
            user_agent=user_agent,
            success=False,
            message="unknown_user",
        )
        await db.commit()
        raise InvalidCredentials("invalid_credentials")

    locked_for = _is_locked(user, now)
    if locked_for > 0:
        await record_audit(
            db,
            action=AuditAction.LOGIN_FAILED,
            actor_user_id=user.id,
            actor_label=user.email,
            ip_address=ip,
            user_agent=user_agent,
            success=False,
            message="account_locked",
            metadata={"retry_after_seconds": locked_for},
        )
        await db.commit()
        raise AccountLocked(locked_for)

    if user.status != UserStatus.ACTIVE.value:
        await record_audit(
            db,
            action=AuditAction.LOGIN_FAILED,
            actor_user_id=user.id,
            actor_label=user.email,
            ip_address=ip,
            user_agent=user_agent,
            success=False,
            message=f"status:{user.status}",
        )
        await db.commit()
        raise AccountSuspended(user.status)

    if not verify_password(password, user.password_hash):
        await _register_failed_login(db, user)
        await record_audit(
            db,
            action=AuditAction.LOGIN_FAILED,
            actor_user_id=user.id,
            actor_label=user.email,
            ip_address=ip,
            user_agent=user_agent,
            success=False,
            message="invalid_password",
            metadata={"failed_count": user.failed_login_count},
        )
        await db.commit()
        raise InvalidCredentials("invalid_credentials")

    # Enforce MFA for SuperAdmin if configured.
    mfa_required = user.mfa_enabled or (
        settings.feature_mfa_required_for_superadmin
        and user.role_code == UserRole.SUPER_ADMIN.value
    )

    if mfa_required:
        if not user.mfa_enabled:
            # SuperAdmin must enroll MFA first — allow login but force enrollment.
            pass
        elif not mfa_code:
            raise MfaRequired(str(user.id))
        else:
            secret = decrypt_str(user.mfa_secret_encrypted or "")
            if not secret or not verify_totp(secret, mfa_code):
                await _register_failed_login(db, user)
                await record_audit(
                    db,
                    action=AuditAction.LOGIN_FAILED,
                    actor_user_id=user.id,
                    actor_label=user.email,
                    ip_address=ip,
                    user_agent=user_agent,
                    success=False,
                    message="invalid_mfa_code",
                )
                await db.commit()
                raise InvalidMfaCode("invalid_mfa_code")

    await _reset_failed_counter(db, user, ip)
    tokens = await _issue_session_tokens(db, user, user_agent, ip)

    await record_audit(
        db,
        action=AuditAction.LOGIN,
        actor_user_id=user.id,
        actor_label=user.email,
        ip_address=ip,
        user_agent=user_agent,
        success=True,
    )
    await db.commit()
    return tokens


async def refresh_tokens(
    db: AsyncSession,
    refresh_token: str,
    *,
    ip: str | None,
    user_agent: str | None,
) -> IssuedTokens:
    try:
        payload = decode_token(refresh_token, expected_type="refresh")
    except ValueError as exc:
        raise InvalidCredentials(str(exc)) from exc

    stmt = select(SysSession).where(SysSession.jti == payload.jti)
    session = (await db.execute(stmt)).scalar_one_or_none()
    if session is None or session.revoked_at is not None:
        raise InvalidCredentials("session_revoked")
    if session.refresh_token_hash != hash_token(refresh_token):
        raise InvalidCredentials("token_mismatch")
    if session.expires_at < datetime.now(timezone.utc):
        raise InvalidCredentials("session_expired")

    user = await _load_user_by_id(db, session.user_id)
    if user is None or user.status != UserStatus.ACTIVE.value:
        raise InvalidCredentials("user_inactive")

    # Rotate: revoke current session and create a fresh pair.
    session.revoked_at = datetime.now(timezone.utc)
    await db.flush()
    tokens = await _issue_session_tokens(db, user, user_agent, ip)
    await db.commit()
    return tokens


async def revoke_session(db: AsyncSession, refresh_token: str) -> bool:
    try:
        payload = decode_token(refresh_token, expected_type="refresh")
    except ValueError:
        return False
    stmt = select(SysSession).where(SysSession.jti == payload.jti)
    session = (await db.execute(stmt)).scalar_one_or_none()
    if session is None or session.revoked_at is not None:
        return False
    session.revoked_at = datetime.now(timezone.utc)
    await db.commit()
    return True


# ---------------------------- MFA enrollment --------------------------------
def _qr_png_base64(uri: str) -> str:
    import qrcode

    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


async def start_mfa_enrollment(user: SysUser) -> dict[str, Any]:
    secret = generate_totp_secret()
    uri = totp_provisioning_uri(secret, user.email)
    return {
        "secret": secret,
        "otpauth_uri": uri,
        "qr_png_base64": _qr_png_base64(uri),
    }


async def confirm_mfa_enrollment(
    db: AsyncSession, user: SysUser, secret: str, code: str
) -> list[str]:
    if not verify_totp(secret, code):
        raise InvalidMfaCode("invalid_mfa_code")
    backup_codes = generate_backup_codes()
    user.mfa_secret_encrypted = encrypt_str(secret)
    user.mfa_backup_codes_encrypted = encrypt_str(",".join(backup_codes))
    user.mfa_enabled = True
    user.mfa_enrolled_at = datetime.now(timezone.utc)

    await record_audit(
        db,
        action=AuditAction.MFA_SETUP,
        actor_user_id=user.id,
        actor_label=user.email,
        success=True,
    )
    await db.commit()
    return backup_codes


async def disable_mfa(db: AsyncSession, user: SysUser) -> None:
    user.mfa_enabled = False
    user.mfa_secret_encrypted = None
    user.mfa_backup_codes_encrypted = None
    user.mfa_enrolled_at = None
    await db.commit()


# ---------------------------- Password ops ----------------------------------
async def change_password(
    db: AsyncSession, user: SysUser, current_password: str, new_password: str
) -> None:
    if not verify_password(current_password, user.password_hash):
        raise InvalidCredentials("invalid_current_password")
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    user.password_changed_at = datetime.now(timezone.utc)
    await db.commit()
