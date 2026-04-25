"""Password hashing, JWT handling and TOTP utilities."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt as bcrypt_lib
import pyotp
from jose import JWTError, jwt
from passlib.context import CryptContext
from passlib.hash import sha512_crypt as imap_sha512_passlib

from app.core.config import get_settings

try:
    import crypt as libc_crypt  # Unix: mismo crypt(3) que Dovecot en Debian
except ImportError:  # pragma: no cover
    libc_crypt = None  # type: ignore[misc, assignment]

settings = get_settings()

pwd_context = CryptContext(
    schemes=["argon2"],
    deprecated="auto",
    argon2__rounds=3,
    argon2__memory_cost=65536,
    argon2__parallelism=4,
)

# IMAP: nuevas contraseñas = BLF-CRYPT ({BLF-CRYPT}$2b$…) — Dovecot 2.3+ lo verifica en nativo;
# con passdb SQL, $6$ a veces fallaba aunque psql y verify_imap_password fueran correctos. Legado: $6$.
IMAP_BCRYPT_ROUNDS = 10
IMAP_SHA512_ROUNDS = 5000
DOVECOT_BCRYPT_PREFIX = "{BLF-CRYPT}"
DOVECOT_SHA512_PREFIX = "{SHA512-CRYPT}"


# ---------------------------- passwords --------------------------------------
def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


def hash_imap_password(plain: str) -> str:
    """Solo `gw_accounts.imap_password_hash` (Dovecot). No usar para `sys_users`.

    Nuevas: ``{BLF-CRYPT}`` + hash bcrypt (lib Python = mismo algoritmo que Dovecot 2.3+).
    Legado: filas con ``$6$`` siguen en :func:`verify_imap_password` y en Dovecot vía ``CRYPT``.
    """
    if len(plain) < 10:
        raise ValueError("password_too_short")
    raw = bcrypt_lib.hashpw(
        plain.encode("utf-8"),
        bcrypt_lib.gensalt(rounds=IMAP_BCRYPT_ROUNDS),
    ).decode("ascii")
    if not raw.startswith(("$2a$", "$2b$", "$2y$")):
        raise ValueError("imap_bcrypt_unexpected")
    return f"{DOVECOT_BCRYPT_PREFIX}{raw}"


def verify_imap_password(plain: str, stored: str) -> bool:
    """Verifica IMAP: BLF-CRYPT ($2*), SHA512-CRYPT ($6$), Argon2 legado."""
    if not stored:
        return False
    s = stored.strip()
    if s.startswith(DOVECOT_SHA512_PREFIX):
        s = s[len(DOVECOT_SHA512_PREFIX) :]
    if s.startswith("$6$"):
        try:
            if libc_crypt is not None and hasattr(libc_crypt, "METHOD_SHA512"):
                return libc_crypt.crypt(plain, s) == s
            return imap_sha512_passlib.verify(plain, s)
        except Exception:
            return False
    if s.startswith(DOVECOT_BCRYPT_PREFIX):
        s = s[len(DOVECOT_BCRYPT_PREFIX) :]
    if s.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            return bcrypt_lib.checkpw(plain.encode("utf-8"), s.encode("ascii"))
        except Exception:
            return False
    try:
        return pwd_context.verify(plain, stored)
    except Exception:
        return False


# ---------------------------- JWT --------------------------------------------
@dataclass(slots=True)
class TokenPayload:
    sub: str
    jti: str
    type: str
    role: str
    exp: int
    iat: int
    extra: dict[str, Any]


def _encode(claims: dict[str, Any]) -> str:
    return jwt.encode(claims, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(
    user_id: str, role: str, jti: str | None = None, **extra: Any
) -> tuple[str, str, datetime]:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=settings.jwt_access_minutes)
    jti = jti or secrets.token_urlsafe(16)
    claims = {
        "sub": user_id,
        "jti": jti,
        "type": "access",
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        **extra,
    }
    return _encode(claims), jti, exp


def create_refresh_token(user_id: str, role: str, jti: str | None = None) -> tuple[str, str, datetime]:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(days=settings.jwt_refresh_days)
    jti = jti or secrets.token_urlsafe(24)
    claims = {
        "sub": user_id,
        "jti": jti,
        "type": "refresh",
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return _encode(claims), jti, exp


def decode_token(token: str, expected_type: str | None = None) -> TokenPayload:
    try:
        raw = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise ValueError(f"Invalid token: {exc}") from exc
    if expected_type and raw.get("type") != expected_type:
        raise ValueError(f"Expected token type '{expected_type}', got '{raw.get('type')}'")
    return TokenPayload(
        sub=str(raw.get("sub")),
        jti=str(raw.get("jti")),
        type=str(raw.get("type")),
        role=str(raw.get("role", "")),
        iat=int(raw.get("iat", 0)),
        exp=int(raw.get("exp", 0)),
        extra={k: v for k, v in raw.items() if k not in {"sub", "jti", "type", "role", "iat", "exp"}},
    )


def hash_token(token: str) -> str:
    """SHA-256 of a token — stored in DB to detect re-use without keeping raw."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ---------------------------- TOTP (MFA) -------------------------------------
def generate_totp_secret() -> str:
    return pyotp.random_base32()


def totp_provisioning_uri(secret: str, email: str, issuer: str = "MSA Backup Commander") -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer)


def verify_totp(secret: str, code: str, valid_window: int = 1) -> bool:
    try:
        return pyotp.TOTP(secret).verify(code, valid_window=valid_window)
    except Exception:
        return False


def generate_backup_codes(n: int = 8) -> list[str]:
    return [f"{secrets.randbelow(10**4):04d}-{secrets.randbelow(10**4):04d}" for _ in range(n)]


# ---------------------------- magic links ------------------------------------
def generate_magic_token() -> tuple[str, str]:
    """Returns (plaintext, sha256_hex_of_plaintext)."""
    plain = secrets.token_urlsafe(32)
    return plain, hashlib.sha256(plain.encode("utf-8")).hexdigest()


def constant_time_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


# ---------------------------- lockout ----------------------------------------
def compute_lockout_seconds(failed_attempts: int) -> int:
    """Exponential lockout policy.

    - 1..4: no lock
    - 5..9: 60s
    - 10..14: 300s (5 min)
    - 15..19: 1800s (30 min)
    - 20+: 86400s (24 h)
    """
    if failed_attempts < 5:
        return 0
    if failed_attempts < 10:
        return 60
    if failed_attempts < 15:
        return 300
    if failed_attempts < 20:
        return 1800
    return 86400
