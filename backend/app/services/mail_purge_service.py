"""Purga de datos locales de correo (Maildir, trabajo GYB, logs Gmail en BD, tokens webmail)."""
from __future__ import annotations

import asyncio
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accounts import GwAccount
from app.models.enums import BackupScope
from app.models.tasks import BackupLog
from app.models.webmail import WebmailAccessToken
from app.services.maildir_paths import maildir_home_from_email, maildir_root_for_account
from app.services.maildir_service import clear_maildir_tree, gyb_workdir_has_eml_or_mbox

PURGE_ALL_MAIL_LOCAL_CONFIRM_PHRASE = "ELIMINAR_TODAS_LAS_COPIAS_LOCALES_DE_CORREO"


def gyb_work_root_for_email(email: str) -> Path:
    return Path(f"/var/msa/work/gmail/{email.strip()}")


def _purge_gyb_workdir_contents(work_root: Path) -> None:
    """Vacía el directorio de trabajo GYB conservando la raíz (misma lógica que backup_engine)."""
    if not work_root.is_dir():
        work_root.mkdir(parents=True, exist_ok=True)
        return
    for child in work_root.iterdir():
        if child.is_file() or child.is_symlink():
            child.unlink(missing_ok=True)
        else:
            shutil.rmtree(child, ignore_errors=False)


def _dir_size_walk(path: Path) -> int | None:
    """Suma ``st_size`` de archivos bajo ``path`` (``os.walk``, sin seguir symlinks)."""
    if not path.is_dir():
        return None
    total = 0
    try:
        for dirpath, _dirnames, filenames in os.walk(path, followlinks=False):
            for name in filenames:
                fp = Path(dirpath) / name
                try:
                    if not fp.is_file():
                        continue
                    total += int(fp.stat().st_size)
                except OSError:
                    continue
    except OSError:
        return None
    return total


def compute_gyb_work_disk_totals(work_root: Path) -> tuple[int | None, int | None, int]:
    """Totales bajo la carpeta GYB local.

    Returns
    -------
    total_bytes
        Todos los archivos regulares; ``None`` si no existe la carpeta.
    export_bytes
        Solo ``.eml`` y ``.mbox`` (mismo criterio que el visor).
    export_count
        Cantidad de archivos ``.eml``/``.mbox``.
    """
    if not work_root.is_dir():
        return None, None, 0
    total_all = 0
    export_bytes = 0
    export_count = 0
    try:
        for dirpath, _dirnames, filenames in os.walk(work_root, followlinks=False):
            for name in filenames:
                fp = Path(dirpath) / name
                try:
                    if not fp.is_file():
                        continue
                    sz = int(fp.stat().st_size)
                except OSError:
                    continue
                total_all += sz
                low = name.lower()
                if low.endswith(".eml") or low.endswith(".mbox"):
                    export_bytes += sz
                    export_count += 1
    except OSError:
        return None, (export_bytes if export_count else None), export_count
    return total_all, export_bytes, export_count


def scan_gyb_work_for_list_row(work_root: Path) -> tuple[bool, int]:
    """Un solo ``os.walk`` para el listado GYB: ¿hay export? + bytes totales en disco.

    Evita duplicar un recorrido completo (antes: ``gyb_workdir_has_eml_or_mbox`` + totales).
    """
    if not work_root.is_dir():
        return False, 0
    has_export = False
    total_all = 0
    try:
        for dirpath, _dirnames, filenames in os.walk(work_root, followlinks=False):
            for name in filenames:
                fp = Path(dirpath) / name
                try:
                    if not fp.is_file():
                        continue
                    sz = int(fp.stat().st_size)
                except OSError:
                    continue
                total_all += sz
                low = name.lower()
                if low.endswith(".eml") or low.endswith(".mbox"):
                    has_export = True
    except OSError:
        return False, 0
    return has_export, total_all


def gyb_work_export_exists_quick(work_root: Path) -> bool:
    """True si hay al menos un ``.eml``/``.mbox`` bajo ``work_root``; deja de recorrer al encontrar uno."""
    if not work_root.is_dir():
        return False
    try:
        for dirpath, _dirnames, filenames in os.walk(work_root, followlinks=False):
            for name in filenames:
                low = name.lower()
                if low.endswith(".eml") or low.endswith(".mbox"):
                    return True
    except OSError:
        return False
    return False


# Alias legado (maildir / otros callers)
_dir_size = _dir_size_walk


def _maildir_has_layout(root: Path) -> bool:
    return all((root / sub).is_dir() for sub in ("cur", "new", "tmp"))


async def count_gmail_logs_for_account(db: AsyncSession, account_id: uuid.UUID) -> int:
    q = await db.execute(
        select(func.count())
        .select_from(BackupLog)
        .where(BackupLog.account_id == account_id, BackupLog.scope == BackupScope.GMAIL.value)
    )
    return int(q.scalar_one() or 0)


async def count_webmail_tokens_for_account(db: AsyncSession, account_id: uuid.UUID) -> int:
    q = await db.execute(
        select(func.count())
        .select_from(WebmailAccessToken)
        .where(WebmailAccessToken.account_id == account_id)
    )
    return int(q.scalar_one() or 0)


def _inventory_disk_sizes(
    root: Path,
    gyb: Path,
    *,
    maildir_has_layout: bool,
    gyb_is_dir: bool,
) -> tuple[int | None, int | None, int | None, int]:
    maildir_sz = _dir_size_walk(root) if maildir_has_layout else None
    if not gyb_is_dir:
        return maildir_sz, None, None, 0
    gyb_total, gyb_export_b, gyb_export_n = compute_gyb_work_disk_totals(gyb)
    display_sz = gyb_total if gyb_total is not None else gyb_export_b
    return maildir_sz, display_sz, gyb_export_b, gyb_export_n


async def build_mail_inventory(db: AsyncSession, account: GwAccount) -> dict:
    root = maildir_root_for_account(account)
    gyb = gyb_work_root_for_email(account.email)
    on_disk = _maildir_has_layout(root)
    has_msg_db = (gyb / "msg-db.sqlite").is_file()
    has_eml = gyb_workdir_has_eml_or_mbox(gyb)
    gyb_exists = gyb.is_dir()
    maildir_size_bytes, gyb_work_size_bytes, gyb_export_bytes, gyb_export_count = await asyncio.to_thread(
        _inventory_disk_sizes,
        root,
        gyb,
        maildir_has_layout=on_disk,
        gyb_is_dir=gyb_exists,
    )
    return {
        "account_id": str(account.id),
        "email": account.email,
        "maildir_root": str(root),
        "maildir_on_disk": on_disk,
        "maildir_size_bytes": maildir_size_bytes,
        "gyb_work_path": str(gyb),
        "gyb_work_has_content": gyb_exists and any(gyb.iterdir()),
        "gyb_work_size_bytes": gyb_work_size_bytes,
        "gyb_work_export_size_bytes": gyb_export_bytes,
        "gyb_work_export_file_count": gyb_export_count,
        "gyb_work_has_msg_db": has_msg_db,
        "gyb_work_has_eml_export": has_eml,
        "gmail_backup_logs_count": await count_gmail_logs_for_account(db, account.id),
        "webmail_tokens_count": await count_webmail_tokens_for_account(db, account.id),
        "imap_enabled": account.imap_enabled,
        "imap_password_configured": bool((account.imap_password_hash or "").strip()),
        "drive_vault_folder_id": (account.drive_vault_folder_id or "").strip() or None,
    }


@dataclass(slots=True)
class AccountMailPurgeOptions:
    maildir: bool = False
    gyb_workdir: bool = False
    gmail_backup_logs: bool = False
    webmail_tokens: bool = False
    revoke_imap_credentials: bool = False


async def purge_account_mail_local(
    db: AsyncSession,
    *,
    account: GwAccount,
    opts: AccountMailPurgeOptions,
) -> dict[str, int | bool]:
    counts: dict[str, int | bool] = {
        "maildir_cleared": 0,
        "gyb_workdir_cleared": 0,
        "gmail_logs_deleted": 0,
        "webmail_tokens_deleted": 0,
        "imap_credentials_revoked": False,
    }

    if opts.maildir:
        if not (account.maildir_path or "").strip():
            account.maildir_path = maildir_home_from_email(account.email)
        await asyncio.to_thread(clear_maildir_tree, maildir_root_for_account(account))
        account.maildir_user_cleared_at = datetime.now(UTC)
        account.total_messages_cache = 0
        account.total_bytes_cache = 0
        counts["maildir_cleared"] = 1

    if opts.gyb_workdir:
        gyb = gyb_work_root_for_email(account.email)
        await asyncio.to_thread(_purge_gyb_workdir_contents, gyb)
        counts["gyb_workdir_cleared"] = 1

    if opts.gmail_backup_logs:
        r = await db.execute(
            delete(BackupLog).where(
                BackupLog.account_id == account.id,
                BackupLog.scope == BackupScope.GMAIL.value,
            )
        )
        counts["gmail_logs_deleted"] = int(r.rowcount or 0)

    if opts.webmail_tokens:
        r2 = await db.execute(delete(WebmailAccessToken).where(WebmailAccessToken.account_id == account.id))
        counts["webmail_tokens_deleted"] = int(r2.rowcount or 0)

    if opts.revoke_imap_credentials:
        account.imap_password_hash = None
        account.imap_enabled = False
        account.imap_password_set_at = None
        account.imap_failed_attempts = 0
        account.imap_locked_until = None
        counts["imap_credentials_revoked"] = True

    await db.flush()
    return counts


async def purge_all_local_mail_data(db: AsyncSession) -> dict[str, int]:
    """Todas las cuentas Workspace: Maildir, trabajo GYB, logs Gmail (BD) y tokens webmail.

    No elimina filas de ``gw_accounts`` ni usuarios de plataforma (``sys_users``).
    No borra datos en Google Drive / Gmail en la nube.
    """
    r_logs = await db.execute(
        delete(BackupLog).where(BackupLog.scope == BackupScope.GMAIL.value)
    )
    gmail_logs_deleted = int(r_logs.rowcount or 0)
    r_tok = await db.execute(delete(WebmailAccessToken))
    webmail_tokens_deleted = int(r_tok.rowcount or 0)

    stmt = select(GwAccount)
    accounts = (await db.execute(stmt)).scalars().all()
    maildirs_cleared = 0
    gyb_cleared = 0
    now = datetime.now(UTC)

    for acc in accounts:
        if not (acc.maildir_path or "").strip():
            acc.maildir_path = maildir_home_from_email(acc.email)
        try:
            await asyncio.to_thread(clear_maildir_tree, maildir_root_for_account(acc))
            maildirs_cleared += 1
        except OSError:
            pass
        try:
            await asyncio.to_thread(_purge_gyb_workdir_contents, gyb_work_root_for_email(acc.email))
            gyb_cleared += 1
        except OSError:
            pass
        acc.maildir_user_cleared_at = now
        acc.total_messages_cache = 0
        acc.total_bytes_cache = 0

    await db.flush()
    return {
        "workspace_accounts": len(accounts),
        "maildirs_cleared": maildirs_cleared,
        "gyb_workdirs_cleared": gyb_cleared,
        "gmail_backup_logs_deleted": gmail_logs_deleted,
        "webmail_tokens_deleted": webmail_tokens_deleted,
    }
