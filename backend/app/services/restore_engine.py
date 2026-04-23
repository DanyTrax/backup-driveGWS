"""Restore execution engine for Drive and Gmail.

Scopes supported:
  * DRIVE_TOTAL          – mirror full account vault back to source Drive.
  * DRIVE_SELECTIVE      – restore specific file IDs from the vault.
  * GMAIL_MBOX_BULK      – re-upload entire Gmail history via gyb restore-mbox.
  * GMAIL_MESSAGE        – single-message restore (selected by Message-ID).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accounts import GwAccount
from app.models.enums import RestoreScope, RestoreStatus
from app.models.restore import RestoreJob
from app.services import gyb_service, rclone_service
from app.services.progress_bus import publish


async def _mark(
    db: AsyncSession,
    job: RestoreJob,
    *,
    status: RestoreStatus,
    error: str | None = None,
    items_restored: int | None = None,
    bytes_restored: int | None = None,
) -> None:
    job.status = status.value
    if status in (RestoreStatus.SUCCESS, RestoreStatus.FAILED, RestoreStatus.CANCELLED):
        job.finished_at = datetime.now(timezone.utc)
    if error:
        job.error_summary = error[:10000]
    if items_restored is not None:
        job.items_restored = items_restored
    if bytes_restored is not None:
        job.bytes_restored = bytes_restored
    await db.flush()


async def restore_drive_job(
    db: AsyncSession, *, job: RestoreJob, celery_task_id: str | None = None
) -> dict[str, Any]:
    job.started_at = datetime.now(timezone.utc)
    job.celery_task_id = celery_task_id
    await _mark(db, job, status=RestoreStatus.RUNNING)
    await publish(f"restore:{job.id}", {"stage": "start", "kind": "drive"})

    account = (
        await db.execute(select(GwAccount).where(GwAccount.id == job.target_account_id))
    ).scalar_one()
    vault = account.drive_vault_folder_id
    if not vault:
        await _mark(db, job, status=RestoreStatus.FAILED, error="missing_vault_folder")
        await db.commit()
        return {"ok": False, "error": "missing_vault_folder"}

    try:
        async with rclone_service.build_rclone_config(
            db, impersonate_email=account.email, vault_folder_id=vault
        ) as cfg:
            argv = rclone_service.build_rclone_argv(
                cfg,
                mode="copy" if job.scope == RestoreScope.DRIVE_SELECTIVE.value else "sync",
                dry_run=job.dry_run,
            )
            # For selective restores we rely on --files-from file list.
            if job.scope == RestoreScope.DRIVE_SELECTIVE.value:
                ids = (job.selection_json or {}).get("file_ids") or []
                if not ids:
                    await _mark(db, job, status=RestoreStatus.FAILED, error="no_files_selected")
                    await db.commit()
                    return {"ok": False, "error": "no_files_selected"}
                # rclone can't filter by file-id, so we operate on paths stored in the vault.
                paths = (job.selection_json or {}).get("paths") or []
                if not paths:
                    await _mark(db, job, status=RestoreStatus.FAILED, error="no_paths_selected")
                    await db.commit()
                    return {"ok": False, "error": "no_paths_selected"}
                list_path = Path(f"/tmp/restore_{job.id}.lst")
                list_path.write_text("\n".join(paths), encoding="utf-8")
                argv = rclone_service.build_rclone_argv(
                    cfg,
                    mode="copy",
                    dry_run=job.dry_run,
                    extra_flags=["--files-from", str(list_path), "--no-traverse"],
                )

            # For Drive restore we invert direction: dest -> source.
            src_idx = argv.index(cfg.remote_source)
            dst_idx = argv.index(cfg.remote_dest)
            argv[src_idx], argv[dst_idx] = argv[dst_idx], argv[src_idx]

            rc, output = await rclone_service.run_rclone(argv)
            if rc != 0:
                await _mark(
                    db, job, status=RestoreStatus.FAILED,
                    error=f"rclone_rc={rc}\n{output[-4000:]}",
                )
                await publish(f"restore:{job.id}", {"stage": "failed"})
                await db.commit()
                return {"ok": False, "rc": rc}
    except Exception as exc:  # pragma: no cover
        await _mark(db, job, status=RestoreStatus.FAILED, error=str(exc))
        await publish(f"restore:{job.id}", {"stage": "failed", "error": str(exc)})
        await db.commit()
        return {"ok": False, "error": str(exc)}

    await _mark(db, job, status=RestoreStatus.SUCCESS)
    await publish(f"restore:{job.id}", {"stage": "done"})
    await db.commit()
    return {"ok": True}


async def restore_gmail_job(
    db: AsyncSession, *, job: RestoreJob, celery_task_id: str | None = None
) -> dict[str, Any]:
    job.started_at = datetime.now(timezone.utc)
    job.celery_task_id = celery_task_id
    await _mark(db, job, status=RestoreStatus.RUNNING)

    account = (
        await db.execute(select(GwAccount).where(GwAccount.id == job.target_account_id))
    ).scalar_one()
    work_root = Path(f"/var/msa/work/restore/{job.id}")
    work_root.mkdir(parents=True, exist_ok=True)

    try:
        async with gyb_service.prepare_gyb_workspace(
            db, account_email=account.email, local_folder=str(work_root)
        ) as workspace:
            extra: list[str] = []
            if job.scope == RestoreScope.GMAIL_MESSAGE.value:
                message_id = (job.selection_json or {}).get("message_id")
                if not message_id:
                    await _mark(db, job, status=RestoreStatus.FAILED, error="missing_message_id")
                    await db.commit()
                    return {"ok": False, "error": "missing_message_id"}
                extra = ["--search", f"Rfc822msgid:{message_id}"]

            label = (job.selection_json or {}).get("label_after") or "Restored"
            if job.apply_restored_label:
                extra += ["--label-restored", label]

            argv = gyb_service.build_gyb_argv(
                workspace,
                email=account.email,
                action="restore",
                extra_flags=extra,
            )
            rc, output = await gyb_service.run_gyb(argv)
            if rc != 0:
                await _mark(
                    db, job, status=RestoreStatus.FAILED,
                    error=f"gyb_rc={rc}\n{output[-4000:]}",
                )
                await db.commit()
                return {"ok": False, "rc": rc}
    except Exception as exc:  # pragma: no cover
        await _mark(db, job, status=RestoreStatus.FAILED, error=str(exc))
        await db.commit()
        return {"ok": False, "error": str(exc)}

    await _mark(db, job, status=RestoreStatus.SUCCESS)
    await db.commit()
    return {"ok": True}
