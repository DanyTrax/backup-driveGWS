"""Convert GYB exports into Maildir layouts served by Dovecot."""
from __future__ import annotations

import email
import email.utils
import hashlib
import mailbox
import os
import re
import shutil
import time
from dataclasses import dataclass
from email.message import Message
from pathlib import Path


_SAFE = re.compile(r"[^A-Za-z0-9_.-]")


def _safe_folder(label: str) -> str:
    return _SAFE.sub("_", label.strip()) or "INBOX"


def _maildir(path: Path) -> mailbox.Maildir:
    md = mailbox.Maildir(str(path), create=True)
    for sub in ("cur", "new", "tmp"):
        Path(path, sub).mkdir(parents=True, exist_ok=True)
    return md


def ensure_maildir_layout(maildir_root: Path) -> None:
    """Crea cur/new/tmp; idempotente.

    No usa ``mailbox.Maildir(create=True)`` aquí: en volúmenes Docker compartidos a veces
    falla con permisos o locks; bastan directorios vacíos para Dovecot.
    """
    maildir_root.mkdir(parents=True, exist_ok=True)
    for sub in ("cur", "new", "tmp"):
        (maildir_root / sub).mkdir(parents=True, exist_ok=True)


def clear_maildir_tree(maildir_root: Path) -> None:
    """Borra el árbol Maildir y deja solo cur/new/tmp vacíos (Dovecot)."""
    if maildir_root.exists():
        shutil.rmtree(maildir_root)
    _maildir(maildir_root)


@dataclass(slots=True)
class MaildirImportStats:
    mbox_files: int = 0
    eml_files: int = 0
    messages: int = 0
    folders: int = 0
    skipped_duplicates: int = 0


def _message_digest(raw: bytes) -> str:
    return hashlib.sha1(raw).hexdigest()


def _add_rfc822_to_maildirs(
    msg: Message,
    raw: bytes,
    *,
    maildir_root: Path,
    default: mailbox.Maildir,
    seen: set[str],
    stats: MaildirImportStats,
) -> None:
    digest = _message_digest(raw)
    if digest in seen:
        stats.skipped_duplicates += 1
        return
    seen.add(digest)

    labels = msg.get("X-Gmail-Labels") or msg.get("X-GMAIL-LABELS") or ""
    targets: list[mailbox.Maildir] = [default]
    if labels:
        for label in [l.strip() for l in str(labels).split(",") if l.strip()]:
            folder = _safe_folder(label)
            sub_path = maildir_root / f".{folder}"
            targets.append(_maildir(sub_path))
            stats.folders += 1
    for md in targets:
        md.add(msg)
    stats.messages += 1


def import_mbox_tree_to_maildir(
    *,
    mbox_root: Path,
    maildir_root: Path,
) -> MaildirImportStats:
    """Importa un directorio de backup GYB hacia Maildir.

    GYB reciente guarda cada mensaje como ``.eml`` bajo ``YYYY/M/D/<id>.eml``.
    Versiones antiguas usaban ``.mbox``. Se procesan ambos formatos.
    """
    stats = MaildirImportStats()
    seen: set[str] = set()
    maildir_root.mkdir(parents=True, exist_ok=True)
    default = _maildir(maildir_root)

    for mbox_file in mbox_root.rglob("*.mbox"):
        stats.mbox_files += 1
        box = mailbox.mbox(str(mbox_file))
        for msg in box:
            raw = bytes(msg.as_bytes())
            _add_rfc822_to_maildirs(
                msg, raw, maildir_root=maildir_root, default=default, seen=seen, stats=stats
            )

    for eml_path in mbox_root.rglob("*.eml"):
        stats.eml_files += 1
        raw = eml_path.read_bytes()
        if not raw.strip():
            continue
        msg = email.message_from_bytes(raw)
        _add_rfc822_to_maildirs(
            msg, raw, maildir_root=maildir_root, default=default, seen=seen, stats=stats
        )

    return stats
