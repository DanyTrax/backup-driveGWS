"""Sube un informe de ejecución exitosa a ``3-REPORTS/logs`` en el vault de la cuenta."""
from __future__ import annotations

import logging
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import rclone_service, vault_layout
from app.services.vault_report_text import build_success_report_text

if TYPE_CHECKING:
    from app.models.accounts import GwAccount
    from app.models.tasks import BackupLog, BackupTask

logger = logging.getLogger(__name__)


async def upload_backup_success_report(
    db: AsyncSession,
    *,
    task: BackupTask,
    account: GwAccount,
    log: BackupLog,
    drive_rclone_dest_subpath: str | None = None,
    dry_run: bool = False,
    report_note_lines: list[str] | None = None,
) -> str | None:
    """Escribe un ``.txt`` bajo ``3-REPORTS/logs/``. Errores: solo log WARNING; no lanza.

    Devuelve la ruta relativa en el vault (p. ej. ``3-REPORTS/logs/backup-....txt``) o ``None``.
    """
    if dry_run:
        return None
    if not vault_layout.vault_success_reports_enabled(task.filters_json):
        return None
    vault_id = (account.drive_vault_folder_id or "").strip()
    if not vault_id:
        return None

    text = build_success_report_text(
        task=task,
        account=account,
        log=log,
        drive_rclone_dest_subpath=drive_rclone_dest_subpath,
        report_note_lines=report_note_lines,
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    safe_scope = (log.scope or "scope").replace("/", "-")[:48]
    fname = f"backup-{stamp}_{safe_scope}_{log.id}.txt"
    base = vault_layout.vault_reports_logs_base_subpath()

    tmpdir = Path(tempfile.mkdtemp(prefix="msa_vault_report_"))
    final_path = tmpdir / fname
    try:
        final_path.write_text(text, encoding="utf-8")
        async with rclone_service.build_rclone_vault_dest_only_config(
            db, vault_folder_id=vault_id
        ) as push_cfg:
            mk_argv = rclone_service.build_rclone_mkdir_dest_argv(
                push_cfg, dest_subpath=base
            )
            mk_rc, mk_out = await rclone_service.run_rclone(mk_argv, cancel_log_id=None)
            if mk_rc != 0:
                logger.warning(
                    "informe vault: mkdir %s rc=%s\n%s",
                    base,
                    mk_rc,
                    mk_out[-2000:],
                )
                return None
            pargv = rclone_service.build_rclone_local_to_vault_argv(
                str(final_path),
                push_cfg,
                dest_subpath=base,
                dry_run=False,
            )
            rc, out = await rclone_service.run_rclone(pargv, cancel_log_id=None)
            if rc != 0:
                logger.warning(
                    "informe vault: copy %s rc=%s\n%s",
                    fname,
                    rc,
                    out[-2000:],
                )
                return None
    except Exception as exc:  # pragma: no cover
        logger.warning("informe vault: excepción al subir %s: %s", fname, exc, exc_info=True)
        return None
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    return f"{base}/{fname}"
