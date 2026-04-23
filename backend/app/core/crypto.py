"""Symmetric encryption helpers (Fernet) for secrets at rest.

Used by:
  * sys_settings rows flagged as encrypted (service account JSON, tokens...).
  * gw_accounts.encrypted_refresh_token (legacy OAuth path).

The master key lives in settings.fernet_key. Rotation is supported by wrapping
multiple keys in a MultiFernet later (Fase 2).
"""
from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


class DecryptionError(RuntimeError):
    """Raised when a ciphertext cannot be decrypted with the current key."""


@lru_cache
def _fernet() -> Fernet:
    key = get_settings().fernet_key
    if not key:
        raise RuntimeError("FERNET_KEY is not configured; refusing to start.")
    return Fernet(key.encode("utf-8") if isinstance(key, str) else key)


def encrypt_str(plaintext: str) -> str:
    """Return a url-safe base64 ciphertext suitable for TEXT columns."""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_str(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:  # pragma: no cover
        raise DecryptionError("Invalid ciphertext or wrong FERNET_KEY.") from exc


def encrypt_bytes(plaintext: bytes) -> bytes:
    return _fernet().encrypt(plaintext)


def decrypt_bytes(ciphertext: bytes) -> bytes:
    try:
        return _fernet().decrypt(ciphertext)
    except InvalidToken as exc:  # pragma: no cover
        raise DecryptionError("Invalid ciphertext or wrong FERNET_KEY.") from exc
