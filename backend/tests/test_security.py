"""Smoke tests for auth primitives."""
from __future__ import annotations

import os

os.environ.setdefault("SECRET_KEY", "a" * 40)
os.environ.setdefault("FERNET_KEY", "gAAAAABmQ8J3xYqmVpPrMbH6vQ2m4vGj4bQNfXt9UmWQwQKzZkuN9xU=")
os.environ.setdefault("POSTGRES_USER", "msa")
os.environ.setdefault("POSTGRES_PASSWORD", "msa")
os.environ.setdefault("POSTGRES_DB", "msa")


def test_password_roundtrip() -> None:
    from app.core.security import hash_password, verify_password

    hashed = hash_password("TopSecret#2024Long!")
    assert verify_password("TopSecret#2024Long!", hashed)
    assert not verify_password("wrong", hashed)


def test_imap_password_bcrypt_dovecot_compat() -> None:
    from app.core.security import (
        DOVECOT_BCRYPT_PREFIX,
        hash_imap_password,
        verify_imap_password,
        verify_password,
    )

    plain = "IMAP-Min10chars!"
    h = hash_imap_password(plain)
    assert h.startswith("$2a$")
    assert verify_imap_password(plain, h)
    assert not verify_imap_password("wrong", h)
    # no confundir con hash de plataforma (Argon2)
    assert not verify_password(plain, h)
    # legado: prefijo explícito Dovecot
    legacy = f"{DOVECOT_BCRYPT_PREFIX}{h}"
    assert verify_imap_password(plain, legacy)


def test_jwt_roundtrip() -> None:
    from app.core.security import create_access_token, decode_token

    token, jti, _ = create_access_token("user-1", "super_admin")
    payload = decode_token(token, expected_type="access")
    assert payload.sub == "user-1"
    assert payload.role == "super_admin"
    assert payload.jti == jti


def test_totp_verify() -> None:
    import pyotp

    from app.core.security import generate_totp_secret, verify_totp

    secret = generate_totp_secret()
    code = pyotp.TOTP(secret).now()
    assert verify_totp(secret, code)


def test_lockout_policy() -> None:
    from app.core.security import compute_lockout_seconds

    assert compute_lockout_seconds(0) == 0
    assert compute_lockout_seconds(4) == 0
    assert compute_lockout_seconds(5) == 60
    assert compute_lockout_seconds(10) == 300
    assert compute_lockout_seconds(15) == 1800
    assert compute_lockout_seconds(20) == 86400
