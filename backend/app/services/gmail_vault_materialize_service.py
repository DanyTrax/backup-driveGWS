"""Materializar ZIPs del vault Gmail (1-GMAIL/zips) en disco local para el visor (Fase 5)."""
from __future__ import annotations

import asyncio
import logging
import shutil
import uuid
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.accounts import GwAccount
from app.models.gmail_vault import GmailVaultMaterialization
from app.models.tasks import BackupTask, backup_task_accounts
from app.services.gmail_vault_materialize_logic import (
    GmailVaultMaterializeError,
    VaultZipIndexEntry,
    merge_materialized_session_into_gyb_workdir,
    parse_lsjson_zip_entries,
    select_zip_entries_for_window,
)
from app.services.gmail_vault_zip_layout import (
    gmail_vault_zip_account_dir_rel,
    gmail_vault_zip_object_rel_from_lsjson,
)
from app.services.progress_bus import publish
from app.services.rclone_service import (
    RcloneConfig,
    _gmail_vault_compare_argv_part,
    _gmail_vault_extra_flags_argv_part,
    _gmail_vault_tps_argv_part,
    build_rclone_vault_dest_only_config,
    rclone_stats_line_progress_pct,
    run_rclone,
)

log = logging.getLogger(__name__)

GYB_WORK_MAIL_PARENT = Path("/var/msa/work/gmail")


def _vault_zips_lsjson_remote(account_id: uuid.UUID) -> str:
    sub = gmail_vault_zip_account_dir_rel(account_id).strip().strip("/")
    return f"dest:{sub}/"


async def rclone_lsjson_zips_for_account(
    cfg: RcloneConfig,
    account_id: uuid.UUID,
) -> list[VaultZipIndexEntry]:
    remote = _vault_zips_lsjson_remote(account_id)
    s = get_settings()
    argv: list[str] = [
        "lsjson",
        remote,
        "-R",
        "--config",
        cfg.config_path,
        "--fast-list",
    ]
    if s.rclone_gmail_vault_no_traverse:
        argv.append("--no-traverse")
    argv += _gmail_vault_tps_argv_part(s)
    argv += _gmail_vault_compare_argv_part(s)
    argv += _gmail_vault_extra_flags_argv_part(s)
    rc, out = await run_rclone(argv, timeout=600)
    if rc != 0:
        raise GmailVaultMaterializeError((out or "rclone_lsjson_failed")[:2000])
    return parse_lsjson_zip_entries(out)


def materialization_paths(account_id: uuid.UUID, session_id: uuid.UUID) -> Path:
    base = Path(get_settings().gmail_vault_materialize_base_path)
    return (base / str(account_id) / str(session_id)).resolve()


def _safe_under_base(full: Path, base: Path) -> bool:
    try:
        full.relative_to(base)
        return True
    except ValueError:
        return False


async def verify_task_linked_to_account(
    db: AsyncSession,
    *,
    task_id: uuid.UUID,
    account_id: uuid.UUID,
) -> None:
    task = (
        await db.execute(select(BackupTask).where(BackupTask.id == task_id))
    ).scalar_one_or_none()
    if task is None:
        raise GmailVaultMaterializeError("task_not_found")
    if task.scope not in ("gmail", "full"):
        raise GmailVaultMaterializeError("task_scope_must_be_gmail_or_full")
    stmt = select(backup_task_accounts.c.account_id).where(
        backup_task_accounts.c.task_id == task_id,
        backup_task_accounts.c.account_id == account_id,
    )
    if (await db.execute(stmt)).scalar_one_or_none() is None:
        raise GmailVaultMaterializeError("task_not_linked_to_account")


async def create_materialization_session(
    db: AsyncSession,
    *,
    account_id: uuid.UUID,
    task_id: Optional[uuid.UUID],
    requested_mode: str,
    window_start: date,
    window_end: date,
    ttl_days: int,
    created_by_user_id: Optional[uuid.UUID],
) -> GmailVaultMaterialization:
    acc = (
        await db.execute(select(GwAccount).where(GwAccount.id == account_id))
    ).scalar_one_or_none()
    if acc is None:
        raise GmailVaultMaterializeError("account_not_found")
    vid = (acc.drive_vault_folder_id or "").strip()
    if not vid:
        raise GmailVaultMaterializeError("missing_drive_vault_folder_id")

    if task_id is not None:
        await verify_task_linked_to_account(db, task_id=task_id, account_id=account_id)

    sid = uuid.uuid4()
    local_root = materialization_paths(account_id, sid)
    ttl = max(1, ttl_days)
    row = GmailVaultMaterialization(
        id=sid,
        account_id=account_id,
        task_id=task_id,
        created_by_user_id=created_by_user_id,
        requested_mode=requested_mode,
        date_from=window_start,
        date_to=window_end,
        ttl_expires_at=datetime.now(timezone.utc) + timedelta(days=ttl),
        path_local=str(local_root),
        status="pending",
        progress_json={
            "phase": "pending",
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "planned_zips": 0,
            "done_zips": 0,
        },
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


def _build_copy_one_zip_argv(cfg: RcloneConfig, rel_under_vault_root: str, dest_dir: Path) -> list[str]:
    s = get_settings()
    rel = rel_under_vault_root.strip().lstrip("/")
    remote = f"{cfg.remote_dest.rstrip(':')}:{rel}"
    argv = [
        "copy",
        remote,
        str(dest_dir.resolve()),
        "--config",
        cfg.config_path,
        "--stats",
        "5s",
        "--stats-one-line",
        "--stats-log-level",
        "NOTICE",
        "--transfers",
        str(s.rclone_gmail_vault_transfers),
        "--checkers",
        str(s.rclone_gmail_vault_checkers),
        "--retries",
        "3",
        "--low-level-retries",
        "10",
    ]
    if s.rclone_gmail_vault_no_traverse:
        argv.append("--no-traverse")
    argv += _gmail_vault_tps_argv_part(s)
    argv += _gmail_vault_compare_argv_part(s)
    argv += _gmail_vault_extra_flags_argv_part(s)
    return argv


def _extract_zip_file(zip_path: Path, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest_dir)


async def run_materialization_job(db: AsyncSession, session_id: uuid.UUID, celery_task_id: str) -> None:
    row = (
        await db.execute(select(GmailVaultMaterialization).where(GmailVaultMaterialization.id == session_id))
    ).scalar_one_or_none()
    if row is None:
        log.warning("gmail_vault_materialize missing session %s", session_id)
        return
    acc = (
        await db.execute(select(GwAccount).where(GwAccount.id == row.account_id))
    ).scalar_one_or_none()
    if acc is None:
        row.status = "failed"
        row.error_summary = "account_not_found"
        await db.commit()
        return

    vid = (acc.drive_vault_folder_id or "").strip()
    if not vid:
        row.status = "failed"
        row.error_summary = "missing_drive_vault_folder_id"
        await db.commit()
        return

    local_root = Path(row.path_local).resolve()
    base = Path(get_settings().gmail_vault_materialize_base_path).resolve()
    if not _safe_under_base(local_root, base):
        row.status = "failed"
        row.error_summary = "invalid_path_local"
        await db.commit()
        return

    ws = row.date_from or date.today()
    we = row.date_to or ws
    prog: dict[str, Any] = dict(row.progress_json or {})
    prog["celery_task_id"] = celery_task_id
    prog["phase"] = "downloading"
    row.progress_json = prog
    row.status = "downloading"
    await db.commit()

    sid = str(session_id)
    try:
        await publish(
            sid,
            {
                "stage": "gmail_vault_materialize",
                "phase": "started",
                "account_id": str(row.account_id),
                "celery_task_id": celery_task_id,
            },
        )
    except Exception:
        pass

    try:
        local_root.mkdir(parents=True, exist_ok=True)
        staging = local_root / "staging"
        extracted_root = local_root / "extracted"
        staging.mkdir(exist_ok=True)
        extracted_root.mkdir(exist_ok=True)

        async with build_rclone_vault_dest_only_config(db, vault_folder_id=vid, account=acc) as cfg:
            entries = await rclone_lsjson_zips_for_account(cfg, row.account_id)
            picked = select_zip_entries_for_window(entries, ws, we)
            prog = dict(row.progress_json or {})
            prog["phase"] = "downloading"
            prog["planned_zips"] = len(picked)
            prog["zip_rel_paths"] = [e.rel_path for e in picked]
            prog["done_zips"] = 0
            row.progress_json = prog
            await db.commit()

            try:
                await publish(
                    sid,
                    {
                        "stage": "gmail_vault_materialize",
                        "phase": "downloading",
                        "planned_zips": len(picked),
                        "window_start": ws.isoformat(),
                        "window_end": we.isoformat(),
                    },
                )
            except Exception:
                pass

            if not picked:
                row.status = "failed"
                row.error_summary = "no_matching_zips_in_vault"
                row.progress_json = {**prog, "phase": "failed"}
                await db.commit()
                try:
                    await publish(sid, {"stage": "gmail_vault_materialize", "phase": "failed", "reason": "no_matching_zips"})
                except Exception:
                    pass
                return

            async def _emit_rclone_line(line: str, zip_rel: str, zip_idx: int, zip_total: int) -> None:
                s = line.strip()
                if not s:
                    return
                try:
                    payload: dict[str, Any] = {
                        "stage": "progress",
                        "scope": "gmail",
                        "phase": "vault_materialize_zip_copy",
                        "raw": s,
                        "rclone_mode": "copy",
                        "zip_rel": zip_rel,
                        "zip_index": zip_idx,
                        "zip_total": zip_total,
                    }
                    pct = rclone_stats_line_progress_pct(s)
                    if pct is not None:
                        payload["progress_pct"] = round(pct, 2)
                    await publish(sid, payload)
                except Exception:
                    pass

            def _on_line_factory(zip_rel: str, zip_idx: int, zip_total: int):
                def _on_line(line: str) -> None:
                    if not line.strip():
                        return
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        return
                    loop.create_task(_emit_rclone_line(line, zip_rel, zip_idx, zip_total))

                return _on_line

            for i, ent in enumerate(picked):
                vault_rel = gmail_vault_zip_object_rel_from_lsjson(row.account_id, ent.rel_path)
                try:
                    await publish(
                        sid,
                        {
                            "stage": "gmail_vault_materialize",
                            "phase": "zip_copy_start",
                            "zip_index": i + 1,
                            "zip_total": len(picked),
                            "zip_rel": ent.rel_path,
                            "vault_rel": vault_rel,
                        },
                    )
                except Exception:
                    pass
                argv = _build_copy_one_zip_argv(cfg, vault_rel, staging)
                rc, out = await run_rclone(
                    argv,
                    on_line=_on_line_factory(ent.rel_path, i + 1, len(picked)),
                    timeout=None,
                )
                if rc != 0:
                    row.status = "failed"
                    row.error_summary = (out or "rclone_copy_zip_failed")[:4000]
                    prog = dict(row.progress_json or {})
                    prog["phase"] = "failed"
                    prog["failed_at_rel"] = ent.rel_path
                    row.progress_json = prog
                    await db.commit()
                    try:
                        await publish(
                            sid,
                            {
                                "stage": "gmail_vault_materialize",
                                "phase": "failed",
                                "zip_rel": ent.rel_path,
                                "vault_rel": vault_rel,
                                "error_excerpt": (out or "")[:800],
                            },
                        )
                    except Exception:
                        pass
                    return
                zip_name = Path(ent.rel_path).name
                zpath = staging / zip_name
                if not zpath.is_file():
                    row.status = "failed"
                    row.error_summary = f"missing_after_copy:{zip_name}"
                    await db.commit()
                    try:
                        await publish(
                            sid,
                            {
                                "stage": "gmail_vault_materialize",
                                "phase": "failed",
                                "reason": "missing_after_copy",
                                "zip_rel": ent.rel_path,
                            },
                        )
                    except Exception:
                        pass
                    return
                ext_dir = extracted_root / zip_name[: -len(".zip")]
                await asyncio.to_thread(_extract_zip_file, zpath, ext_dir)
                prog = dict(row.progress_json or {})
                prog["done_zips"] = i + 1
                row.progress_json = prog
                await db.commit()
                try:
                    await publish(
                        sid,
                        {
                            "stage": "gmail_vault_materialize",
                            "phase": "zip_extracted",
                            "done_zips": i + 1,
                            "planned_zips": len(picked),
                            "zip_rel": ent.rel_path,
                        },
                    )
                except Exception:
                    pass

        try:
            await publish(
                sid,
                {
                    "stage": "gmail_vault_materialize",
                    "phase": "ready",
                    "done_zips": len(picked),
                    "planned_zips": len(picked),
                },
            )
        except Exception:
            pass
        row.status = "ready"
        row.progress_json = {**(row.progress_json or {}), "phase": "ready"}
        await db.commit()
    except GmailVaultMaterializeError as exc:
        row.status = "failed"
        row.error_summary = str(exc)[:4000]
        row.progress_json = {**(row.progress_json or {}), "phase": "failed"}
        await db.commit()
        try:
            await publish(
                sid,
                {"stage": "gmail_vault_materialize", "phase": "failed", "error": str(exc)[:500]},
            )
        except Exception:
            pass
    except Exception as exc:
        log.exception("gmail_vault_materialize_job_failed session=%s", session_id)
        row.status = "failed"
        row.error_summary = str(exc)[:4000]
        row.progress_json = {**(row.progress_json or {}), "phase": "failed"}
        await db.commit()
        try:
            await publish(
                sid,
                {"stage": "gmail_vault_materialize", "phase": "failed", "error": str(exc)[:500]},
            )
        except Exception:
            pass


async def promote_materialization_to_gyb_work(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
) -> GmailVaultMaterialization:
    """Fusiona ``extracted/`` en ``/var/msa/work/gmail/<email>/``, borra ZIPs locales y limpia ``extracted/``."""
    row = (
        await db.execute(select(GmailVaultMaterialization).where(GmailVaultMaterialization.id == session_id))
    ).scalar_one_or_none()
    if row is None:
        raise GmailVaultMaterializeError("session_not_found")
    if row.status != "ready":
        raise GmailVaultMaterializeError(f"materialize_not_ready:{row.status}")

    acc = (
        await db.execute(select(GwAccount).where(GwAccount.id == row.account_id))
    ).scalar_one_or_none()
    if acc is None:
        raise GmailVaultMaterializeError("account_not_found")

    from app.services.mail_purge_service import gyb_work_root_for_email

    local_root = Path(row.path_local).resolve()
    base = Path(get_settings().gmail_vault_materialize_base_path).resolve()
    if not _safe_under_base(local_root, base):
        raise GmailVaultMaterializeError("invalid_path_local")

    work_dest = gyb_work_root_for_email(acc.email).resolve()
    gyb_parent = GYB_WORK_MAIL_PARENT.resolve()
    if not _safe_under_base(work_dest, gyb_parent):
        raise GmailVaultMaterializeError("invalid_gyb_work_dest")

    try:
        n = await asyncio.to_thread(merge_materialized_session_into_gyb_workdir, local_root, work_dest)
    except GmailVaultMaterializeError:
        raise
    except Exception as exc:
        log.exception("promote_materialization session=%s", session_id)
        raise GmailVaultMaterializeError(str(exc)[:2000]) from exc

    prog = dict(row.progress_json or {})
    prog["phase"] = "promoted"
    prog["promoted_to_gyb_work"] = str(work_dest)
    prog["promoted_zip_trees_merged"] = n
    prog["promoted_at"] = datetime.now(timezone.utc).isoformat()
    row.progress_json = prog
    row.status = "promoted"
    await db.commit()
    await db.refresh(row)

    sid = str(session_id)
    try:
        await publish(
            sid,
            {
                "stage": "gmail_vault_materialize",
                "phase": "promoted",
                "gyb_work": str(work_dest),
                "merged_trees": n,
            },
        )
    except Exception:
        pass

    return row


async def purge_materialization_local(row: GmailVaultMaterialization) -> None:
    p = Path(row.path_local)
    base = Path(get_settings().gmail_vault_materialize_base_path).resolve()
    if p.is_dir() and _safe_under_base(p.resolve(), base):
        await asyncio.to_thread(shutil.rmtree, p, ignore_errors=True)


async def expire_session_if_ttl_elapsed(db: AsyncSession, row: GmailVaultMaterialization) -> bool:
    """Si pasó el TTL, borra materialización en disco y en BD. Devuelve True si eliminó la fila."""
    now = datetime.now(timezone.utc)
    if row.ttl_expires_at > now:
        return False
    await purge_materialization_local(row)
    await db.delete(row)
    await db.commit()
    return True


async def cleanup_all_expired_materializations(db: AsyncSession) -> int:
    now = datetime.now(timezone.utc)
    stmt = select(GmailVaultMaterialization).where(GmailVaultMaterialization.ttl_expires_at < now)
    rows = list((await db.execute(stmt)).scalars().all())
    n = 0
    for row in rows:
        try:
            await purge_materialization_local(row)
            await db.delete(row)
            n += 1
        except Exception:
            log.exception("cleanup_materialization row=%s", row.id)
    if n:
        await db.commit()
    return n
