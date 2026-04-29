"""Lectura segura de Maildir local (visor en plataforma; mismo árbol que Dovecot)."""
from __future__ import annotations

import email
import re
from dataclasses import dataclass
from email.header import decode_header, make_header
from email.parser import BytesParser
from email.policy import compat32
from pathlib import Path

from app.services.maildir_service import ensure_maildir_subfolder

_FOLDER_ID = re.compile(r"^(\.?[A-Za-z0-9_.-]+|INBOX)$")

# Buzones tipo Gmail/gyb: agrupa variantes en disco (.Sent / .SENT) y nombres en español.
_SYSTEM_FOLDER_GROUP: tuple[tuple[str, frozenset[str], str, str], ...] = (
    ("sent", frozenset({"sent", "sents"}), ".SENT", "Enviados"),
    ("draft", frozenset({"draft", "drafts"}), ".DRAFT", "Borradores"),
    ("spam", frozenset({"spam", "junk"}), ".SPAM", "Spam"),
    (
        "trash",
        frozenset({"trash", "bin", "deleted", "papeleradeborrados"}),
        ".TRASH",
        "Papelera",
    ),
    ("starred", frozenset({"starred", "flagged"}), ".STARRED", "Destacados"),
    ("important", frozenset({"important"}), ".IMPORTANT", "Importantes"),
)


def _system_label(group_id: str) -> str:
    for gid, _vars, _canon, lab in _SYSTEM_FOLDER_GROUP:
        if gid == group_id:
            return lab
    return group_id


def _system_group_for_subfolder(folder_id: str) -> str | None:
    if folder_id == "INBOX" or not folder_id.startswith("."):
        return None
    base = folder_id[1:].lower()
    compact = base.replace("_", "")
    for gid, variants, _canon, _lab in _SYSTEM_FOLDER_GROUP:
        if base in variants or any(compact == v.replace("_", "") for v in variants):
            return gid
    if "gmail" in base and "trash" in base:
        return "trash"
    if "gmail" in base and "spam" in base:
        return "spam"
    if "gmail" in base and ("sent" in base or "enviado" in base):
        return "sent"
    if "gmail" in base and ("draft" in base or "borrador" in base):
        return "draft"
    return None


def _has_maildir_mailbox(p: Path) -> bool:
    return (p / "cur").is_dir() or (p / "new").is_dir()


def _decode_mime_header(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:  # pragma: no cover
        return value


def _safe_folder_path(maildir_root: Path, folder_id: str) -> Path:
    fid = (folder_id or "").strip() or "INBOX"
    if fid == "INBOX":
        root = maildir_root.resolve()
        if not (root / "cur").is_dir() and not (root / "new").is_dir():
            raise ValueError("not_maildir")
        return root
    if not _FOLDER_ID.match(fid) or ".." in fid:
        raise ValueError("invalid_folder_id")
    sub = maildir_root / fid
    resolved = sub.resolve()
    if not resolved.is_relative_to(maildir_root.resolve()):
        raise ValueError("invalid_folder_id")
    if not (resolved / "cur").is_dir() and not (resolved / "new").is_dir():
        raise ValueError("not_maildir")
    return resolved


def list_maildir_folders(maildir_root: Path) -> list[tuple[str, str]]:
    """``(folder_id, display_name)``. INBOX primero; hijos ``.Label``; buzones Gmail estándar aunque estén vacíos."""
    out: list[tuple[str, str]] = []
    root = maildir_root.resolve()
    if not root.is_dir():
        return out

    if _has_maildir_mailbox(root):
        out.append(("INBOX", "Bandeja de entrada"))

    covered_system: set[str] = set()
    for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_dir() or not child.name.startswith("."):
            continue
        if not _has_maildir_mailbox(child):
            continue
        fid = child.name
        sg = _system_group_for_subfolder(fid)
        if sg:
            covered_system.add(sg)
            out.append((fid, _system_label(sg)))
        else:
            out.append((fid, fid[1:].replace("_", " ")))

    for gid, _variants, canon_id, label in _SYSTEM_FOLDER_GROUP:
        if gid in covered_system:
            continue
        dest = root / canon_id
        try:
            if not _has_maildir_mailbox(dest):
                ensure_maildir_subfolder(dest)
        except OSError:
            continue
        if not _has_maildir_mailbox(dest):
            continue
        out.append((canon_id, label))
        covered_system.add(gid)

    seen: set[str] = set()
    deduped: list[tuple[str, str]] = []
    for fid, name in out:
        if fid in seen:
            continue
        seen.add(fid)
        deduped.append((fid, name))

    inbox_row = next(((i, n) for i, n in deduped if i == "INBOX"), None)
    rest = sorted([x for x in deduped if x[0] != "INBOX"], key=lambda t: t[1].casefold())
    if inbox_row:
        return [inbox_row, *rest]
    return rest


@dataclass
class MessageListItem:
    key: str
    subject: str
    from_addr: str
    date_display: str | None
    size: int


def _headers_from_file(path: Path, max_bytes: int = 96_000) -> tuple[str, str, str | None]:
    data = path.read_bytes()[:max_bytes]
    msg = email.message_from_bytes(data, policy=compat32)
    subject = _decode_mime_header(msg.get("Subject"))
    from_ = _decode_mime_header(msg.get("From"))
    date = msg.get("Date")
    return subject, from_, date


def list_messages(
    maildir_root: Path,
    *,
    folder_id: str,
    limit: int = 80,
    offset: int = 0,
) -> list[MessageListItem]:
    folder = _safe_folder_path(maildir_root, folder_id)
    cur = folder / "cur"
    new = folder / "new"
    files: list[tuple[float, Path]] = []
    for d in (cur, new):
        if not d.is_dir():
            continue
        for p in d.iterdir():
            if p.is_file():
                try:
                    st = p.stat()
                    files.append((st.st_mtime_ns, p))
                except OSError:
                    continue
    files.sort(key=lambda x: -x[0])
    slice_ = files[offset : offset + max(1, min(limit, 500))]
    out: list[MessageListItem] = []
    for _mt, path in slice_:
        try:
            subject, from_, date = _headers_from_file(path)
        except OSError:
            continue
        out.append(
            MessageListItem(
                key=path.name,
                subject=subject or "(sin asunto)",
                from_addr=from_ or "—",
                date_display=date,
                size=path.stat().st_size if path.exists() else 0,
            )
        )
    return out


@dataclass
class MessageBody:
    key: str
    subject: str
    from_addr: str
    date_display: str | None
    text_plain: str | None
    text_html: str | None


def _extract_body(msg: email.message.Message) -> tuple[str | None, str | None]:
    plain_parts: list[str] = []
    html_parts: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = (part.get_content_type() or "").lower()
            if ctype == "text/plain" and not part.get_filename():
                try:
                    pl = part.get_payload(decode=True)
                    if pl:
                        charset = part.get_content_charset() or "utf-8"
                        plain_parts.append(pl.decode(charset, errors="replace"))
                except Exception:
                    continue
            elif ctype == "text/html" and not part.get_filename():
                try:
                    hl = part.get_payload(decode=True)
                    if hl:
                        charset = part.get_content_charset() or "utf-8"
                        html_parts.append(hl.decode(charset, errors="replace"))
                except Exception:
                    continue
    else:
        ctype = (msg.get_content_type() or "").lower()
        try:
            raw = msg.get_payload(decode=True)
            if raw:
                charset = msg.get_content_charset() or "utf-8"
                text = raw.decode(charset, errors="replace")
                if ctype == "text/html":
                    html_parts.append(text)
                else:
                    plain_parts.append(text)
        except Exception:
            pass
    pl = "\n\n".join(plain_parts).strip() or None
    hl = "\n<hr>\n".join(html_parts).strip() or None
    return pl, hl


def read_message(maildir_root: Path, *, folder_id: str, message_key: str) -> MessageBody:
    folder = _safe_folder_path(maildir_root, folder_id)
    key = message_key.strip()
    if not key or "/" in key or key == "." or ".." in key:
        raise ValueError("invalid_message_key")
    for sub in ("cur", "new"):
        path = folder / sub / key
        if path.is_file():
            raw = path.read_bytes()
            msg = BytesParser(policy=compat32).parsebytes(raw)
            subject = _decode_mime_header(msg.get("Subject")) or "(sin asunto)"
            from_ = _decode_mime_header(msg.get("From")) or "—"
            date = msg.get("Date")
            tpl, thtml = _extract_body(msg)
            return MessageBody(
                key=key,
                subject=subject,
                from_addr=from_,
                date_display=date,
                text_plain=tpl,
                text_html=thtml,
            )
    raise FileNotFoundError("message_not_found")
