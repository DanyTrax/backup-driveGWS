"""Archivo de logo subido en volumen persistente (p. ej. /data/branding)."""
from __future__ import annotations

import os
from pathlib import Path

BRANDING_DIR = Path(os.environ.get("BRANDING_STORAGE_DIR", "/data/branding")).resolve()
LOGO_PREFIX = "logo."
ALLOWED_LOGO_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"})
MAX_LOGO_BYTES = 2 * 1024 * 1024


def _logo_candidates() -> list[Path]:
    if not BRANDING_DIR.is_dir():
        return []
    return sorted(p for p in BRANDING_DIR.glob(f"{LOGO_PREFIX}*") if p.is_file())


def has_uploaded_logo() -> bool:
    return bool(_logo_candidates())


def uploaded_logo_path() -> Path | None:
    candidates = _logo_candidates()
    return candidates[0] if candidates else None


def delete_uploaded_logo() -> None:
    for p in _logo_candidates():
        p.unlink(missing_ok=True)


def guess_suffix(filename: str) -> str:
    low = (filename or "").lower().strip()
    for suf in sorted(ALLOWED_LOGO_SUFFIXES, key=len, reverse=True):
        if low.endswith(suf):
            return suf
    return ""


def media_type_for_suffix(suffix: str) -> str:
    s = suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
    }.get(s, "application/octet-stream")
