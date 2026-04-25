"""Webmail provisioning, magic links and SSO handoff to Roundcube."""
from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

from jose import jwt
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.redis_client import get_redis
from app.core.security import generate_magic_token, hash_password
from app.models.accounts import GwAccount
from app.models.enums import WebmailTokenPurpose
from app.models.webmail import WebmailAccessToken


settings = get_settings()
logger = logging.getLogger(__name__)


class SSORedisUnavailableError(RuntimeError):
    """Redis inaccesible o error al volcar el JWT/ rid consumido por el plugin msa_sso."""


# Mensaje fijo; el 503 y el cuerpo detail sustituyen al 500 opaco.
_SSO_REDIS_USER_HINT = (
    "Comprobar en el host: el contenedor app debe resolver REDIS_HOST y REDIS_PASSWORD "
    "(misma pila que docker-compose) y el servicio redis en marcha. "
    "Si el panel carga y Celery no, a menudo faltó redis_url correcto o contraseña con caracteres especiales sin escapar."
)


def _webmail_base_url() -> str:
    """Solo DOMAIN_WEBMAIL (Roundcube, SSO msa_sso). No confundir con platform_public_origin."""
    w = settings.webmail_public_origin
    if w:
        return w
    return "https://webmail.example.com"


def _magic_redeem_public_url(*, token: str, purpose: str) -> str:
    """URL pública: debe ser la API bajo DOMAIN_PLATFORM (`/api/...`), no el host de Roundcube."""
    from urllib.parse import quote

    q_tok = quote(token, safe="")
    q_pur = quote(purpose, safe="")
    base = settings.platform_public_origin
    if base:
        return f"{base}/api/webmail/magic-redeem?token={q_tok}&purpose={q_pur}"
    # Último recurso: mismo origen que webmail (solo si NPM enruta /api al backend bajo el host de webmail).
    base_wm = _webmail_base_url().rstrip("/")
    return f"{base_wm}/api/webmail/magic-redeem?token={q_tok}&purpose={q_pur}"


# ---------------------------------------------------------------------------
# Magic links (first_setup / password_reset / client_sso)
# ---------------------------------------------------------------------------
PASSWORD_ASSIGN_TTL_MAX_MINUTES = 24 * 60

# Propósitos cuyo token sirve en la landing /webmail/assign-password (fijar clave IMAP en la plataforma).
# Incluye `first_setup` / `password_reset` del «magic link» aunque la URL de redeem sea otra, por si
# solo copian el parámetro token a la página de asignación.
_PURPOSES_SET_IMAP_VIA_LANDING: frozenset[str] = frozenset(
    {
        WebmailTokenPurpose.PASSWORD_ASSIGN.value,
        WebmailTokenPurpose.FIRST_SETUP.value,
        WebmailTokenPurpose.PASSWORD_RESET.value,
    }
)


async def issue_magic_link(
    db: AsyncSession,
    *,
    account: GwAccount,
    purpose: WebmailTokenPurpose,
    ttl_minutes: int = 60,
    issued_by_user_id: str | None = None,
) -> dict[str, Any]:
    plain, digest = generate_magic_token()

    token_row = WebmailAccessToken(
        account_id=account.id,
        purpose=purpose.value,
        token_hash=digest,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes),
        issued_by_user_id=uuid.UUID(issued_by_user_id) if issued_by_user_id else None,
    )
    db.add(token_row)
    await db.flush()

    url = _magic_redeem_public_url(token=plain, purpose=purpose.value)
    return {
        "token": plain,
        "url": url,
        "expires_at": token_row.expires_at.isoformat(),
    }


async def issue_password_assign_link(
    db: AsyncSession,
    *,
    account: GwAccount,
    site_root: str,
    ttl_minutes: int,
    issued_by_user_id: str | None = None,
) -> dict[str, Any]:
    """Enlace a la landing bajo DOMAIN_PLATFORM (`/webmail/assign-password`); luego usan la clave en Roundcube (DOMAIN_WEBMAIL)."""
    ttl = max(5, min(int(ttl_minutes), PASSWORD_ASSIGN_TTL_MAX_MINUTES))
    plain, digest = generate_magic_token()
    now = datetime.now(timezone.utc)
    token_row = WebmailAccessToken(
        account_id=account.id,
        purpose=WebmailTokenPurpose.PASSWORD_ASSIGN.value,
        token_hash=digest,
        expires_at=now + timedelta(minutes=ttl),
        issued_by_user_id=uuid.UUID(issued_by_user_id) if issued_by_user_id else None,
    )
    db.add(token_row)
    await db.flush()
    q = quote(plain, safe="")
    base = site_root.rstrip("/")
    url = f"{base}/webmail/assign-password?token={q}"
    return {
        "token": plain,
        "url": url,
        "expires_at": token_row.expires_at,
        "ttl_minutes": ttl,
    }


@dataclass
class PasswordSetupPeek:
    """Resultado de `peek_password_setup` (sin consumir el token)."""
    ok: bool
    email: str | None = None
    expires_at: datetime | None = None
    reason: str | None = None  # not_found, wrong_purpose, consumed, expired, revoked, no_account


async def peek_password_setup(
    db: AsyncSession, *, token: str
) -> PasswordSetupPeek:
    """Valida el token (sin consumir) para `GET /password-setup/status`."""
    if not (token and token.strip()):
        return PasswordSetupPeek(ok=False, reason="not_found")
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    row = (await db.execute(select(WebmailAccessToken).where(WebmailAccessToken.token_hash == digest))).scalar_one_or_none()
    if row is None:
        return PasswordSetupPeek(ok=False, reason="not_found")
    pur = str(row.purpose)
    if pur not in _PURPOSES_SET_IMAP_VIA_LANDING:
        return PasswordSetupPeek(ok=False, reason="wrong_purpose")
    acc = (await db.execute(select(GwAccount).where(GwAccount.id == row.account_id))).scalar_one_or_none()
    if acc is None:
        return PasswordSetupPeek(ok=False, reason="no_account")
    now = datetime.now(timezone.utc)
    if row.revoked_at is not None:
        return PasswordSetupPeek(ok=False, reason="revoked", email=acc.email)
    if row.consumed_at is not None:
        return PasswordSetupPeek(
            ok=False, reason="consumed", email=acc.email, expires_at=row.expires_at
        )
    if row.expires_at < now:
        return PasswordSetupPeek(ok=False, reason="expired", email=acc.email, expires_at=row.expires_at)
    return PasswordSetupPeek(
        ok=True, email=acc.email, expires_at=row.expires_at, reason=None
    )


async def complete_password_setup(
    db: AsyncSession,
    *,
    token: str,
    plaintext: str,
    consumer_ip: str | None,
    consumer_user_agent: str | None,
) -> uuid.UUID:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    row = (await db.execute(select(WebmailAccessToken).where(WebmailAccessToken.token_hash == digest))).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if row is None or str(row.purpose) not in _PURPOSES_SET_IMAP_VIA_LANDING:
        raise ValueError("invalid_token")
    if row.consumed_at is not None or row.revoked_at is not None:
        raise ValueError("token_already_used")
    if row.expires_at < now:
        raise ValueError("token_expired")

    acc = (await db.execute(select(GwAccount).where(GwAccount.id == row.account_id))).scalar_one()
    await set_webmail_password(db, account=acc, plaintext=plaintext)
    row.consumed_at = now
    row.consumer_ip = consumer_ip
    row.consumer_user_agent = (consumer_user_agent or "")[:400] or None
    await db.flush()
    return acc.id


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
    raw = jwt.encode(
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
    # python-jose devuelve str; si algún entorno diera bytes, Redis y el plugin PHP exigen str.
    token = raw.decode("ascii") if isinstance(raw, (bytes, bytearray)) else str(raw)
    try:
        redis = get_redis()
        # URL corta vía `rid` en Redis: evita WAF/«Block Common Exploits» (URLs largas con JWT) y
        # límites de query; el plugin acepta también `token=` (compatibilidad).
        await redis.setex(f"sso:jti:{jti}", ttl_seconds + 10, "pending")
        rid = secrets.token_urlsafe(32)
        await redis.setex(f"sso:rid:{rid}", ttl_seconds + 30, token)
    except RedisError as exc:
        logger.exception("issue_sso_jwt: fallo al escribir en Redis (jti=%s, rid=…)", jti)
        raise SSORedisUnavailableError(
            f"Redis no respondió al emitir SSO. {_SSO_REDIS_USER_HINT} Detalle: {exc!s}"
        ) from exc
    # index.php asegura que el front controller ejecute el plugin aun con rewrite/proxy.
    base = _webmail_base_url().rstrip("/")
    rid_q = quote(rid, safe="")
    url = f"{base}/index.php?_task=login&_action=plugin.msa_sso&rid={rid_q}"
    return {"token": token, "url": url, "expires_at": exp.isoformat(), "jti": jti, "rid": rid}
