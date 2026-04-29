"""Convert GYB exports into Maildir layouts served by Dovecot."""

from __future__ import annotations

import email
import hashlib
import mailbox
import re
import shutil
import sqlite3
import time
from dataclasses import dataclass
from email.message import Message
from pathlib import Path


_SAFE = re.compile(r"[^A-Za-z0-9_.-]")

# Gmail / GYB: no crear Maildir ``.Label`` para estados o bandejas que ya cubre el INBOX raíz.
_NO_EXTRA_MAILDIR_SUBFOLDERS = frozenset(
    {
        "inbox",
        "unread",
        "starred",
        "important",
        "chats",
        "chat",
    }
)


def _safe_folder(label: str) -> str:
    return _SAFE.sub("_", label.strip()) or "INBOX"


def _header_label_list(msg: Message) -> list[str]:
    labels = msg.get("X-Gmail-Labels") or msg.get("X-GMAIL-LABELS") or ""
    if not labels:
        return []
    return [p.strip() for p in str(labels).split(",") if p.strip()]


def _labels_for_maildir_subfolders(label_list: list[str]) -> list[str]:
    """Etiquetas que merecen una carpeta ``.Nombre`` bajo el Maildir (p. ej. Sent, etiquetas de usuario)."""
    out: list[str] = []
    for raw in label_list:
        s = raw.strip()
        if not s:
            continue
        low = s.lower()
        if low in _NO_EXTRA_MAILDIR_SUBFOLDERS:
            continue
        if s.startswith("^"):  # flags internos de Gmail (p. ej. ^open)
            continue
        if low.startswith("category_"):
            continue
        out.append(s)
    return out


def _load_gyb_sqlite_label_index(mbox_root: Path) -> dict[str, list[str]] | None:
    """Mapeo ``ruta/relativa/eml`` → nombres de etiqueta según ``msg-db.sqlite`` de GYB.

    GYB guarda las etiquetas aquí; muchos ``.eml`` no traen cabecera ``X-Gmail-Labels``. Sin esto,
    todo el correo cae solo en INBOX en el visor Maildir / Dovecot.
    """
    db = (mbox_root / "msg-db.sqlite").resolve()
    if not db.is_file():
        return None
    uri = "file:%s?mode=ro" % db.as_posix()
    conn = sqlite3.connect(uri, uri=True)
    try:
        cur = conn.execute(
            """
            SELECT m.message_filename, l.label
            FROM messages AS m
            INNER JOIN labels AS l ON l.message_num = m.message_num
            """
        )
        out: dict[str, list[str]] = {}
        for fn, lab in cur.fetchall():
            if not fn or not lab:
                continue
            key = str(fn).replace("\\", "/").strip().lstrip("/")
            if not key:
                continue
            bucket = out.setdefault(key, [])
            if lab not in bucket:
                bucket.append(lab)
        return out
    finally:
        conn.close()


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
    sqlite_labels: list[str] | None = None,
) -> None:
    digest = _message_digest(raw)
    if digest in seen:
        stats.skipped_duplicates += 1
        return
    seen.add(digest)

    if sqlite_labels is not None:
        label_sources = sqlite_labels
    else:
        label_sources = _header_label_list(msg)
    targets: list[mailbox.Maildir] = [default]
    for label in _labels_for_maildir_subfolders(label_sources):
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

    Las etiquetas se toman de ``msg-db.sqlite`` (GYB) cuando existe; si no,
    de la cabecera ``X-Gmail-Labels`` (p. ej. Takeout).
    """
    stats = MaildirImportStats()
    seen: set[str] = set()
    maildir_root.mkdir(parents=True, exist_ok=True)
    default = _maildir(maildir_root)
    mbox_resolved = mbox_root.resolve()
    sqlite_index = _load_gyb_sqlite_label_index(mbox_resolved)

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
        rel = eml_path.resolve().relative_to(mbox_resolved).as_posix().replace("\\", "/")
        sqlite_labels: list[str] | None = None
        if sqlite_index is not None and rel in sqlite_index:
            sqlite_labels = sqlite_index[rel]
        _add_rfc822_to_maildirs(
            msg,
            raw,
            maildir_root=maildir_root,
            default=default,
            seen=seen,
            stats=stats,
            sqlite_labels=sqlite_labels,
        )

    return stats
