"""Convención de paths bajo el vault por usuario (Shared Drive, ``drive_vault_folder_id``).

* ``1-GMAIL/``  — acumulado incremental de export GYB (y opcionalmente otras entregas) por cuenta.
* ``2-DRIVE/``  — respaldos de "Mi unidad" (rclone) separados de Gmail.
* ``3-REPORTS/``  — informes y logs de plataforma por cuenta; subcarpetas ``reports/`` y ``logs/``.

Activá ``filters_json.vault_legacy_layout = true`` para el comportamiento previo
(sin prefijos ``1-``/``2-``) en el backup de archivos de Drive; Gmail al vault
requiere tareas nuevas o no usar ``vault_gmail_disable_push``."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# Nombres fijos bajo el vault del usuario
VAULT_DIR_GMAIL = "1-GMAIL"
VAULT_DIR_DRIVE = "2-DRIVE"
VAULT_DIR_REPORTS = "3-REPORTS"
# Bajo 3-REPORTS (creadas al activar backup de la cuenta)
VAULT_REPORTS_SUBDIR_REPORTS = "reports"
VAULT_REPORTS_SUBDIR_LOGS = "logs"

# Ruta relativa bajo 1-GMAIL donde vuelca GYB (single bucket incremental en Drive)
GMAIL_VAULT_GYB_SUBDIR = "gyb_mbox"

# Sincronización continua (sin ``dated_run``) bajo 2-DRIVE
DRIVE_VAULT_CONTINUOUS_DIR = "_sync"


def use_separated_vault_layout(filters: dict[str, Any] | None) -> bool:
    """Si True (default), Drive → ``2-DRIVE/...``; Gmail post-job → ``1-GMAIL/...``."""
    if not filters:
        return True
    if filters.get("vault_legacy_layout") is True:
        return False
    return bool(filters.get("vault_separated_layout", True))


def use_gmail_vault_push(filters: dict[str, Any] | None) -> bool:
    if not filters:
        return True
    if filters.get("vault_gmail_disable_push") is True:
        return False
    if filters.get("vault_legacy_layout") is True:
        return bool(filters.get("vault_gmail_push", False))
    return True


def gmail_purge_gyb_workdir_after_vault_verified(filters: dict[str, Any] | None) -> bool:
    """Si True: tras subir a ``1-GMAIL/gyb_mbox`` se ejecuta ``rclone check``; si pasa, se vacía
    ``/var/msa/work/gmail/<email>/`` en el VPS (no toca Maildir). Requiere push al vault; por defecto False."""
    if not filters:
        return False
    if filters.get("vault_gmail_disable_push") is True:
        return False
    return bool(filters.get("gmail_purge_gyb_workdir_after_vault_verified"))


def gmail_vault_rclone_subpath() -> str:
    """Destino bajo el remoto ``dest:`` = vault del usuario, solo carpeta GYB acumulada."""
    return f"{VAULT_DIR_GMAIL.rstrip('/')}/{GMAIL_VAULT_GYB_SUBDIR.lstrip('/')}"


def drive_vault_base_prefix(filters: dict[str, Any] | None) -> str:
    if use_separated_vault_layout(filters):
        return VAULT_DIR_DRIVE
    return ""


def drive_dest_subpath_for_task(
    filters: dict[str, Any] | None,
    *,
    now: datetime | None = None,
) -> str | None:
    """Subpath bajo el remoto dest (vault de la cuenta) para rclone (sin leading slash)."""
    filters = filters or {}
    now = now or datetime.now(timezone.utc)
    base = drive_vault_base_prefix(filters)

    if not use_separated_vault_layout(filters):
        if filters.get("drive_layout") == "dated_run":
            stamp = now.strftime("%Y-%m-%dT%H-%M")
            prefix = str(filters.get("dated_run_prefix", "MSA_Runs")).strip("/") or "MSA_Runs"
            return f"{prefix}/{stamp}"
        return None

    if filters.get("drive_layout") == "dated_run":
        stamp = now.strftime("%Y-%m-%dT%H-%M")
        prefix = str(filters.get("dated_run_prefix", "MSA_Runs")).strip("/") or "MSA_Runs"
        kind = filters.get("drive_run_kind")
        if kind in ("TOTAL", "SNAPSHOT", "total", "snapshot"):
            k = str(kind).upper()
            folder = f"{stamp} ({k})"
        else:
            folder = stamp
        return f"{base}/{prefix}/{folder}"

    if filters.get("drive_dest_use_continuous_dir", True) is not False:
        return f"{base}/{DRIVE_VAULT_CONTINUOUS_DIR}"
    return f"{base}/"

