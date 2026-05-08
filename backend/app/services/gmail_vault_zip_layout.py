"""Rutas relativas bajo vault para ZIPs Gmail (``1-GMAIL/zips/…``).

Usar con el remoto rclone ``dest:`` cuya raíz es la carpeta de cuenta (``drive_vault_folder_id``).
"""
from __future__ import annotations

import re
import uuid
from datetime import date
from typing import Literal, Optional, Tuple

from app.services.vault_layout import VAULT_DIR_GMAIL

GMAIL_VAULT_ZIPS_SEGMENT = "zips"

# Subcarpeta por tipo de sellado (nombre en Drive; estable para listados y visor).
ZipCadenceDir = Literal["BOOTSTRAP", "WEEKLY", "MONTHLY", "MANUAL"]

_ZIP_BASENAME_RE = re.compile(
    r"^(?P<start>\d{4}-\d{2}-\d{2})__(?P<end>\d{4}-\d{2}-\d{2})\.zip$",
    re.IGNORECASE,
)


def gmail_vault_zips_root_rel() -> str:
    """Root de todos los zips bajo Gmail, p. ej. ``1-GMAIL/zips``."""
    return f"{VAULT_DIR_GMAIL}/{GMAIL_VAULT_ZIPS_SEGMENT}".strip("/")


def gmail_vault_zip_account_dir_rel(account_id: uuid.UUID) -> str:
    """Directorio de una cuenta bajo zips: ``1-GMAIL/zips/{uuid}``."""
    return f"{gmail_vault_zips_root_rel()}/{account_id}".strip("/")


def gmail_vault_zip_cadence_dir_rel(account_id: uuid.UUID, cadence: ZipCadenceDir) -> str:
    """``1-GMAIL/zips/{account_id}/WEEKLY`` (o BOOTSTRAP/MONTHLY/MANUAL)."""
    return f"{gmail_vault_zip_account_dir_rel(account_id)}/{cadence}".strip("/")


def zip_basename_for_period(period_start: date, period_end: date) -> str:
    """``YYYY-MM-DD__YYYY-MM-DD.zip`` (incluyente en manifiesto; el nombre es solo etiqueta)."""
    if period_end < period_start:
        raise ValueError("period_end must be >= period_start")
    return f"{period_start.isoformat()}__{period_end.isoformat()}.zip"


def manifest_basename_for_zip(zip_basename: str) -> str:
    """``foo.zip`` → ``foo.manifest.json``."""
    if not zip_basename.lower().endswith(".zip"):
        raise ValueError("zip_basename must end with .zip")
    return f"{zip_basename[:-4]}.manifest.json"


def gmail_vault_zip_and_manifest_rel(
    account_id: uuid.UUID,
    cadence: ZipCadenceDir,
    period_start: date,
    period_end: date,
) -> Tuple[str, str]:
    """Rutas relativas bajo dest del vault: (path_zip, path_manifest_json)."""
    base = gmail_vault_zip_cadence_dir_rel(account_id, cadence)
    zn = zip_basename_for_period(period_start, period_end)
    mn = manifest_basename_for_zip(zn)
    return (f"{base}/{zn}".strip("/"), f"{base}/{mn}".strip("/"))


def parse_zip_basename_period(zip_basename: str) -> Optional[Tuple[date, date]]:
    """Si el basename cumple el patrón, devuelve (start, end); si no, None."""
    m = _ZIP_BASENAME_RE.match(zip_basename.strip())
    if not m:
        return None
    try:
        d0 = date.fromisoformat(m.group("start"))
        d1 = date.fromisoformat(m.group("end"))
    except ValueError:
        return None
    if d1 < d0:
        return None
    return (d0, d1)


def seal_kind_to_zip_cadence_dir(seal_kind: str) -> ZipCadenceDir:
    """Alinea ``seal_kind`` del manifiesto con el nombre de carpeta en Drive."""
    key = (seal_kind or "").strip().lower()
    m: dict[str, ZipCadenceDir] = {
        "bootstrap": "BOOTSTRAP",
        "weekly": "WEEKLY",
        "monthly": "MONTHLY",
        "manual": "MANUAL",
    }
    if key not in m:
        raise ValueError(f"unknown seal_kind for zip layout: {seal_kind!r}")
    return m[key]
