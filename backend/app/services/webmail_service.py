"""Webmail provisioning, magic links and SSO handoff to Roundcube."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.redis_client import get_redis
from app.core.security import generate_magic_token, hash_password
from app.models.accounts import GwAccount
from app.models.enums import WebmailTokenPurpose
from app.models.webmail import WebmailAccessToken


settings = get_settings()


def _webmail_base_url() -> str:
    if settings.domain_webmail:
        return f"https://{settings.domain_webmail}"
    return "https://webmail.example.com"


# ---------------------------------------------------------------------------
# Magic links (first_setup / password_reset / client_sso)
# ---------------------------------------------------------------------------
async def issue_magic_link(
    db: AsyncSession,
    *,
    account: GwAccount,
    purpose: WebmailTokenPurpose,
    ttl_minutes: int = 60,
    issued_by_user_id: str | None = None,
) -> dict[str, Any]:
    plain, digest = generate_magic_token()
    import uuid

    token_row = WebmailAccessToken(
        account_id=account.id,
        purpose=purpose.value,
        token_hash=digest,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes),
        issued_by_user_id=uuid.UUID(issued_by_user_id) if issued_by_user_id else None,
    )
    db.add(token_row)
    await db.flush()

    url = f"{_webmail_base_url()}/msa/webmail/redeem?token={plain}&purpose={purpose.value}"
    return {
        "token": plain,
        "url": url,
        "expires_at": token_row.expires_at.isoformat(),
    }


async def redeem_magic_link(
    db: AsyncSession,
    *,
    token: str,
    purpose: WebmailTokenPurpose,
    consumer_ip: str | None,
    consumer_user_agent: str | None,
) -> GwAccount:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    stmt = select(WebmailAccessToken).where(WebmailAccessToken.token_hash == digest)
    row = (await db.execute(stmt)).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if row is None or row.purpose != purpose.value:
        raise ValueError("invalid_token")
    if row.consumed_at is not None or row.revoked_at is not None:
        raise ValueError("token_already_used")
    if row.expires_at < now:
        raise ValueError("token_expired")

    acc = (await db.execute(select(GwAccount).where(GwAccount.id == row.account_id))).scalar_one()
    row.consumed_at = now
    row.consumer_ip = consumer_ip
    row.consumer_user_agent = (consumer_user_agent or "")[:400] or None
    await db.flush()
    return acc


# ---------------------------------------------------------------------------
# IMAP / Dovecot password management
# ---------------------------------------------------------------------------
async def set_webmail_password(
    db: AsyncSession, *, account: GwAccount, plaintext: str
) -> None:
    if len(plaintext) < 10:
        raise ValueError("password_too_short")
    account.imap_password_hash = hash_password(plaintext)
    account.imap_password_set_at = datetime.now(timezone.utc)
    account.imap_enabled = True


# ---------------------------------------------------------------------------
# SSO JWT that Roundcube's msa_sso plugin consumes
# ---------------------------------------------------------------------------
SSO_JWT_TYPE_ADMIN = "admin_sso"
SSO_JWT_TYPE_CLIENT = "client_sso"


async def issue_sso_jwt(
    *,
    email: str,
    kind: str,
    ttl_seconds: int = 60,
) -> dict[str, Any]:
    if kind not in {SSO_JWT_TYPE_ADMIN, SSO_JWT_TYPE_CLIENT}:
        raise ValueError(f"unsupported_sso_kind: {kind}")
    jti = secrets.token_urlsafe(16)
    now = datetime.now(timezone.utc)
    exp = now + timedelta(seconds=ttl_seconds)
    token = jwt.encode(
        {
            "sub": email,
            "jti": jti,
            "type": kind,
            "iat": int(now.timestamp()),
            "exp": int(exp.timestamp()),
            "iss": "msa-backup-commander",
        },
        settings.secret_key,
        algorithm="HS256",
    )
    redis = get_redis()
    await redis.setex(f"sso:jti:{jti}", ttl_seconds + 10, "pending")
    url = f"{_webmail_base_url()}/?_action=plugin.msa_sso&token={token}"
    return {"token": token, "url": url, "expires_at": exp.isoformat(), "jti": jti}
