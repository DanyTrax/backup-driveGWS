"""ZIP + manifiesto bajo ``1-GMAIL/zips/`` y actualización de ``GmailVaultAccountState`` (Fase 3)."""
from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import BackupStatus
from app.models.gmail_vault import GmailVaultAccountState
from app.schemas.gmail_vault_manifest import GmailVaultManifestFileEntry, GmailVaultZipManifestV1
from app.services import rclone_service
from app.services.gmail_vault_plan_service import GmailZipUploadDecision
from app.services.gmail_vault_zip_layout import (
    gmail_vault_zip_and_manifest_rel,
    manifest_basename_for_zip,
    zip_basename_for_period,
)
from app.services.progress_bus import publish

if TYPE_CHECKING:
    from app.models.accounts import GwAccount
    from app.models.tasks import BackupLog, BackupTask

_MANIFEST_SKIP = "manifest.sha256"


def overlap_days_from_filters(filters: dict[str, Any] | None) -> int:
    v = (filters or {}).get("overlap_days", 1)
    try:
        return max(0, min(int(v), 366))
    except (TypeError, ValueError):
        return 1


async def load_gmail_vault_account_state(
    db: AsyncSession,
    *,
    account_id: uuid.UUID,
    task_id: uuid.UUID,
) -> Optional[GmailVaultAccountState]:
    stmt = select(GmailVaultAccountState).where(
        GmailVaultAccountState.account_id == account_id,
        GmailVaultAccountState.task_id == task_id,
    ).limit(1)
    return (await db.execute(stmt)).scalar_one_or_none()


async def ensure_gmail_vault_account_state(
    db: AsyncSession,
    *,
    account_id: uuid.UUID,
    task_id: uuid.UUID,
    packaging_mode: str,
) -> GmailVaultAccountState:
    row = await load_gmail_vault_account_state(db, account_id=account_id, task_id=task_id)
    if row is not None:
        row.packaging_mode = packaging_mode
        await db.flush()
        return row
    row = GmailVaultAccountState(
        account_id=account_id,
        task_id=task_id,
        packaging_mode=packaging_mode,
    )
    db.add(row)
    await db.flush()
    return row


def _build_zip_sync(work_root: Path, zip_out: Path) -> list[GmailVaultManifestFileEntry]:
    entries: list[GmailVaultManifestFileEntry] = []
    zip_out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_out, "w", zipfile.ZIP_DEFLATED) as zf:
        paths = sorted(work_root.rglob("*"))
        for path in paths:
            if not path.is_file():
                continue
            rel = path.relative_to(work_root).as_posix()
            if rel == _MANIFEST_SKIP:
                continue
            st = path.stat()
            zf.write(path, rel)
            entries.append(
                GmailVaultManifestFileEntry(
                    rel_path=rel,
                    size_bytes=int(st.st_size),
                    sha256=None,
                )
            )
    return entries


async def run_gmail_zip_vault_push_phase(
    db: AsyncSession,
    *,
    log: "BackupLog",
    task: "BackupTask",
    account: "GwAccount",
    work_root: Path,
    log_id_str: str,
    vault_id: str,
    decision: GmailZipUploadDecision,
    packaging_mode: str,
) -> tuple[bool, Optional[str]]:
    """Comprime ``work_root`` (export GYB), escribe manifiesto v1 y copia ambos al vault."""
    await publish(
        log_id_str,
        {
            "stage": "vault_zip_start",
            "scope": "gmail",
            "period_start": decision.period_start.isoformat(),
            "period_end": decision.period_end.isoformat(),
            "seal_kind": decision.seal_kind,
        },
    )
    zb = zip_basename_for_period(decision.period_start, decision.period_end)
    zip_rel, _man_rel = gmail_vault_zip_and_manifest_rel(
        account.id,
        decision.cadence_dir,
        decision.period_start,
        decision.period_end,
    )
    parent_rel = str(Path(zip_rel).parent.as_posix())

    staging = Path(tempfile.mkdtemp(prefix="msa_gyb_zip_", dir="/tmp"))
    try:
        zip_local = staging / zb
        entries = await asyncio.to_thread(_build_zip_sync, work_root, zip_local)
        overlap = overlap_days_from_filters(task.filters_json)
        manifest = GmailVaultZipManifestV1(
            account_id=account.id,
            account_email=account.email,
            task_id=task.id,
            timezone=task.timezone or "UTC",
            period_start=decision.period_start,
            period_end=decision.period_end,
            overlap_days_applied=overlap,
            seal_kind=decision.seal_kind,  # type: ignore[arg-type]
            backup_log_id=log.id,
            zip_basename=zb,
            files=entries,
        )
        man_name = manifest_basename_for_zip(zb)
        man_local = staging / man_name
        man_local.write_text(
            json.dumps(manifest.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )
        await publish(
            log_id_str,
            {
                "stage": "vault_zip_built",
                "scope": "gmail",
                "zip_basename": zb,
                "files_in_zip": len(entries),
            },
        )

        async with rclone_service.build_rclone_vault_dest_only_config(
            db, vault_folder_id=vault_id
        ) as push_cfg:
            mk_argv = rclone_service.build_rclone_mkdir_dest_argv(
                push_cfg, dest_subpath=parent_rel
            )
            mk_rc, mk_out = await rclone_service.run_rclone(
                mk_argv, cancel_log_id=log_id_str
            )
            await db.refresh(log)
            if log.status == BackupStatus.CANCELLED.value:
                return False, "cancelled"
            if mk_rc != 0:
                return False, f"vault_zip_mkdir_rc={mk_rc}\n{mk_out[-4000:]}"

            async def _emit_zip_vault_rclone(line: str) -> None:
                s = line.strip()
                if not s:
                    return
                try:
                    payload: dict[str, Any] = {
                        "stage": "progress",
                        "scope": "gmail",
                        "phase": "vault_zip_upload",
                        "raw": s,
                    }
                    if (
                        "teamDriveFileLimitExceeded" in s
                        or "file limit for this shared drive has been exceeded"
                        in s.lower()
                    ):
                        payload["stage"] = "vault_drive_file_limit"
                        payload["severity"] = "error"
                        payload["hint_es"] = (
                            "Límite de cantidad de archivos en la unidad compartida de Google "
                            "(≈400 000 ítems). Cada .eml cuenta como un archivo; por eso el uso en GB "
                            "puede ser bajo pero igual se bloquea. Hay que liberar ítems, dividir en "
                            "otra unidad compartida o cambiar la estrategia de export (p. ej. mbox)."
                        )
                    pct = rclone_service.rclone_stats_line_progress_pct(s)
                    if pct is not None:
                        payload["progress_pct"] = round(pct, 2)
                    await publish(log_id_str, payload)
                except Exception:
                    pass

            def _zip_vault_on_line(line: str) -> None:
                if not line.strip():
                    return
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    return
                loop.create_task(_emit_zip_vault_rclone(line))

            argv = rclone_service.build_rclone_local_to_vault_argv(
                str(staging),
                push_cfg,
                dest_subpath=parent_rel,
                dry_run=bool(task.dry_run),
            )
            vrc, vout = await rclone_service.run_rclone(
                argv, on_line=_zip_vault_on_line, cancel_log_id=log_id_str
            )
            await db.refresh(log)
            if log.status == BackupStatus.CANCELLED.value:
                return False, "cancelled"
            if vrc != 0:
                return False, f"vault_zip_rclone_rc={vrc}\n{vout[-4000:]}"

        st_row = await ensure_gmail_vault_account_state(
            db,
            account_id=account.id,
            task_id=task.id,
            packaging_mode=packaging_mode,
        )
        st_row.last_sealed_at = datetime.now(UTC)
        st_row.last_seal_kind = decision.seal_kind
        st_row.last_vault_zip_rel_path = zip_rel
        prev = dict(st_row.watermark_json or {})
        prev.update(
            {
                "last_backup_log_id": str(log.id),
                "period_end": decision.period_end.isoformat(),
                "zip_basename": zb,
            }
        )
        st_row.watermark_json = prev
        await db.flush()

        await publish(
            log_id_str,
            {
                "stage": "vault_zip_done",
                "scope": "gmail",
                "vault_rel_zip": zip_rel,
            },
        )
        return True, None
    finally:
        shutil.rmtree(staging, ignore_errors=True)
