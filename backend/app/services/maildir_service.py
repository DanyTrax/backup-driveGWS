"""Convert GYB exports into Maildir layouts served by Dovecot."""

from __future__ import annotations

import email
import hashlib
import mailbox
import os
import re
import shutil
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from email.message import Message
from pathlib import Path, PurePosixPath


def _normalize_gyb_relative_path(path_str: str) -> str:
    """Clave única para comparar ruta GYB en SQLite vs disco (``YYYY/M/D/id.eml``).

    GYB guarda ``message_filename`` con ``os.path.join`` (puede usar ``\\`` en Windows);
    además puede aparecer prefijo ``./`` o mezclas evitables.
    """
    t = str(path_str).strip().replace("\\", "/")
    while t.startswith("./"):
        t = t[2:]
    t = t.lstrip("/")
    if not t:
        return ""
    parts = [p for p in PurePosixPath(t).parts if p != "."]
    if not parts:
        return ""
    return str(PurePosixPath(*parts))


@dataclass(slots=True)
class GybSqliteLabelIndex:
    """Índices desde ``msg-db.sqlite``: por ruta relativa al backup y por ID de mensaje Gmail."""

    by_relpath: dict[str, list[str]]
    by_message_uid: dict[str, list[str]]


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


def _load_gyb_sqlite_label_index(mbox_root: Path) -> GybSqliteLabelIndex | None:
    """Lee ``msg-db.sqlite`` de GYB: rutas relativas normalizadas + UID Gmail (nombre de ``.eml``).

    Sin esto, los ``.eml`` suelen ir solo a INBOX (no traen ``X-Gmail-Labels``).
    Si la ruta en disco no coincide texto a texto con ``message_filename`` (``\\`` vs ``/``, etc.),
    sigue existiendo el índice por ``uid`` del mensaje.
    """
    db = (mbox_root / "msg-db.sqlite").resolve()
    if not db.is_file():
        return None
    uri = "file:%s?mode=ro" % db.as_posix()
    conn = sqlite3.connect(uri, uri=True)
    try:
        by_relpath: dict[str, list[str]] = {}
        cur = conn.execute(
            """
            SELECT m.message_filename, l.label
            FROM messages AS m
            INNER JOIN labels AS l ON l.message_num = m.message_num
            """
        )
        for fn, lab in cur.fetchall():
            if not fn or not lab:
                continue
            nk = _normalize_gyb_relative_path(fn)
            if not nk:
                continue
            bucket = by_relpath.setdefault(nk, [])
            if lab not in bucket:
                bucket.append(lab)

        by_message_uid: dict[str, list[str]] = {}
        cur2 = conn.execute(
            """
            SELECT u.uid, l.label
            FROM uids AS u
            INNER JOIN labels AS l ON l.message_num = u.message_num
            """
        )
        for uid, lab in cur2.fetchall():
            if not uid or not lab:
                continue
            ukey = str(uid).strip()
            bucket = by_message_uid.setdefault(ukey, [])
            if lab not in bucket:
                bucket.append(lab)

        return GybSqliteLabelIndex(by_relpath=by_relpath, by_message_uid=by_message_uid)
    finally:
        conn.close()


def _merged_label_sources_from_gyb(
    index: GybSqliteLabelIndex | None,
    *,
    norm_rel: str,
    message_uid: str,
    msg: Message,
) -> list[str]:
    header = _header_label_list(msg)
    if index is None:
        return header
    from_sqlite: list[str] = []
    if norm_rel in index.by_relpath:
        from_sqlite.extend(index.by_relpath[norm_rel])
    u = message_uid.strip()
    if u and u in index.by_message_uid:
        for x in index.by_message_uid[u]:
            if x not in from_sqlite:
                from_sqlite.append(x)
    if from_sqlite:
        return list(dict.fromkeys([*from_sqlite, *header]))
    return header


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


def ensure_maildir_subfolder(subfolder: Path) -> None:
    """Crea cur/new/tmp bajo un buzón hijo (p. ej. ``Maildir/.SENT``)."""
    subfolder.mkdir(parents=True, exist_ok=True)
    for sub in ("cur", "new", "tmp"):
        (subfolder / sub).mkdir(parents=True, exist_ok=True)


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


def _iter_maildir_message_files(maildir_root: Path):
    """Itera ficheros de mensajes bajo ``cur/`` y ``new/`` (no ``tmp``)."""
    if not maildir_root.is_dir():
        return
    for dirpath, _dirnames, filenames in os.walk(maildir_root, topdown=True):
        base = Path(dirpath)
        if base.name not in ("cur", "new"):
            continue
        for fn in filenames:
            yield base / fn


def _digest_maildir_file(path: Path) -> str | None:
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if not raw.strip():
        return None
    return _message_digest(raw)


def collect_message_digests_existing_in_maildir(maildir_root: Path) -> set[str]:
    """SHA-1 del cuerpo RFC822 ya presente en Maildir (todas las carpetas).

    Sirve para no volver a insertar los mismos mensajes en backups GYB incrementales:
    GYB deja histórico de ``.eml`` en disco y cada import re-leería todo sin esto.
    """
    paths = list(_iter_maildir_message_files(maildir_root))
    if not paths:
        return set()
    if len(paths) < 96:
        out: set[str] = set()
        for p in paths:
            d = _digest_maildir_file(p)
            if d:
                out.add(d)
        return out
    workers = min(32, max(4, len(paths) // 120))
    out_p: set[str] = set()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(_digest_maildir_file, p) for p in paths]
        for fut in as_completed(futures):
            d = fut.result()
            if d:
                out_p.add(d)
    return out_p


def _add_rfc822_to_maildirs(
    msg: Message,
    raw: bytes,
    *,
    maildir_root: Path,
    default: mailbox.Maildir,
    seen: set[str],
    stats: MaildirImportStats,
    label_sources: list[str],
) -> None:
    digest = _message_digest(raw)
    if digest in seen:
        stats.skipped_duplicates += 1
        return
    seen.add(digest)

    targets: list[mailbox.Maildir] = [default]
    for label in _labels_for_maildir_subfolders(label_sources):
        folder = _safe_folder(label)
        sub_path = maildir_root / f".{folder}"
        targets.append(_maildir(sub_path))
        stats.folders += 1
    for md in targets:
        md.add(msg)
    stats.messages += 1


def count_maildir_message_files(maildir_root: Path) -> int:
    """Número de ficheros de mensaje bajo ``cur/`` y ``new/`` (todas las carpetas)."""
    return sum(1 for _ in _iter_maildir_message_files(maildir_root))


def import_mbox_tree_to_maildir(
    *,
    mbox_root: Path,
    maildir_root: Path,
) -> MaildirImportStats:
    """Importa un directorio de backup GYB hacia Maildir.

    GYB reciente guarda cada mensaje como ``.eml`` bajo ``YYYY/M/D/<id>.eml``.
    Versiones antiguas usaban ``.mbox``. Se procesan ambos formatos.

    Las etiquetas se toman de ``msg-db.sqlite`` (ruta normalizada + UID del ``.eml``)
    mezclado con cabeceras ``X-Gmail-Labels`` cuando existan.

    Idempotencia: antes de importar se indexan los digest SHA-1 de los mensajes ya
    guardados en Maildir; los ``.eml`` cuyo cuerpo coincida no se vuelven a añadir.
    Así los backups GYB incrementales (histórico de ``.eml`` en work) no duplican
    el buzón local. Si cambian solo etiquetas en Gmail sin cambiar el fichero ``.eml``,
    puede hacer falta **Reconstruir Maildir desde GYB** en la UI para refrescar carpetas.
    """
    stats = MaildirImportStats()
    maildir_root.mkdir(parents=True, exist_ok=True)
    seen = collect_message_digests_existing_in_maildir(maildir_root)
    default = _maildir(maildir_root)
    mbox_resolved = mbox_root.resolve()
    sqlite_bundle = _load_gyb_sqlite_label_index(mbox_resolved)

    for mbox_file in mbox_root.rglob("*.mbox"):
        stats.mbox_files += 1
        box = mailbox.mbox(str(mbox_file))
        for msg in box:
            raw = bytes(msg.as_bytes())
            _add_rfc822_to_maildirs(
                msg,
                raw,
                maildir_root=maildir_root,
                default=default,
                seen=seen,
                stats=stats,
                label_sources=_header_label_list(msg),
            )

    for eml_path in mbox_root.rglob("*.eml"):
        stats.eml_files += 1
        raw = eml_path.read_bytes()
        if not raw.strip():
            continue
        msg = email.message_from_bytes(raw)
        norm_rel = _normalize_gyb_relative_path(
            eml_path.resolve().relative_to(mbox_resolved).as_posix()
        )
        message_uid = eml_path.stem
        labels = _merged_label_sources_from_gyb(
            sqlite_bundle,
            norm_rel=norm_rel,
            message_uid=message_uid,
            msg=msg,
        )
        _add_rfc822_to_maildirs(
            msg,
            raw,
            maildir_root=maildir_root,
            default=default,
            seen=seen,
            stats=stats,
            label_sources=labels,
        )

    return stats


def gyb_workdir_has_eml_or_mbox(work_root: Path) -> bool:
    """True si el directorio de trabajo GYB contiene al menos un ``.eml`` o ``.mbox``."""
    if not work_root.is_dir():
        return False
    for p in work_root.rglob("*"):
        if p.is_file() and p.suffix.lower() in (".eml", ".mbox"):
            return True
    return False


def gyb_export_ready_for_maildir_rebuild(work_root: Path) -> tuple[bool, str]:
    """Comprueba si se puede reconstruir Maildir solo con datos locales (sin Gmail)."""
    if not work_root.is_dir():
        return False, "gyb_workdir_missing"
    if not (work_root / "msg-db.sqlite").is_file():
        return False, "gyb_msg_db_missing"
    if not gyb_workdir_has_eml_or_mbox(work_root):
        return False, "gyb_eml_export_missing"
    return True, ""


def rebuild_maildir_from_local_gyb_workdir(
    *,
    work_root: Path,
    maildir_root: Path,
) -> MaildirImportStats:
    """Vuelca de nuevo ``work_root`` (export GYB + msg-db.sqlite) sobre Maildir.

    Borra el contenido previo del Maildir (como ``clear_maildir_tree``) y reimporta con la
    lógica actual de etiquetas (evita tener que bajar otra vez de Gmail si el GYB local sigue íntegro).
    """
    ok, code = gyb_export_ready_for_maildir_rebuild(work_root)
    if not ok:
        raise ValueError(code)
    clear_maildir_tree(maildir_root)
    return import_mbox_tree_to_maildir(mbox_root=work_root, maildir_root=maildir_root)
