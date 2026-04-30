"""Lectura segura de Maildir local (visor en plataforma; mismo árbol que Dovecot)."""
from __future__ import annotations

import base64
import email
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from email.header import decode_header, make_header
from email.parser import BytesParser
from email.policy import compat32
from email.utils import parsedate_to_datetime
from pathlib import Path

from app.services.maildir_service import ensure_maildir_subfolder

_FOLDER_ID = re.compile(r"^(\.?[A-Za-z0-9_.-]+|INBOX)$")

# Tope por imagen inline para inyectar en HTML como data: (evita respuestas enormes).
_MAX_INLINE_IMAGE_BYTES = 1_572_864  # ~1.5 MiB

_CID_SRC_RE = re.compile(r"\bcid:([^\"\'\s>]+)", re.IGNORECASE)

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


def _parsed_epoch_from_date_header(date_raw: str | None) -> float | None:
    if not date_raw or not str(date_raw).strip():
        return None
    try:
        dt = parsedate_to_datetime(str(date_raw).strip())
        if dt is None:
            return None
        return dt.timestamp()
    except (TypeError, ValueError, OverflowError):
        return None


def _maildir_matches_query(subject: str, from_addr: str, q_lower: str) -> bool:
    if not q_lower:
        return True
    return q_lower in subject.lower() or q_lower in from_addr.lower()


# Una fila para ordenar por Date: (sort_key, mtime_ns, path, subject, from, date_raw).
MaildirHeaderRow = tuple[float, int, Path, str, str, str | None]


def _maildir_header_row(mtime_ns: int, p: Path) -> MaildirHeaderRow | None:
    try:
        subject, from_, date_hdr = _headers_from_file(p)
    except OSError:
        return None
    ep = _parsed_epoch_from_date_header(date_hdr)
    sort_key = ep if ep is not None else (mtime_ns / 1e9)
    return (sort_key, mtime_ns, p, subject or "", from_ or "", date_hdr)


def _collect_header_rows_parallel(raw: list[tuple[int, Path]]) -> list[MaildirHeaderRow]:
    """Lee cabeceras de todos los ficheros; en paralelo si hay bastantes (carpetas grandes)."""
    if not raw:
        return []
    if len(raw) < 48:
        out: list[MaildirHeaderRow] = []
        for mtime_ns, p in raw:
            row = _maildir_header_row(mtime_ns, p)
            if row:
                out.append(row)
        return out
    workers = min(32, max(4, len(raw) // 80))
    out_parallel: list[MaildirHeaderRow] = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(_maildir_header_row, mt, p) for mt, p in raw]
        for fut in as_completed(futures):
            row = fut.result()
            if row:
                out_parallel.append(row)
    return out_parallel


def list_messages(
    maildir_root: Path,
    *,
    folder_id: str,
    limit: int = 80,
    offset: int = 0,
    q: str | None = None,
    sort_by: str = "header_date",
    sort_order: str = "desc",
) -> list[MessageListItem]:
    """Lista mensajes Maildir en ``cur`` y ``new``.

    Por defecto se ordena por la cabecera ``Date`` del mensaje (``sort_by=header_date``), que es lo
    que suele coincidir con la fecha mostrada en la lista. Si no se puede parsear ``Date``, se usa
    el mtime del fichero como clave secundaria.

    Con ``sort_by=mtime`` solo se usa la fecha de modificación del fichero en disco.

    ``sort_order``: ``desc`` = más reciente primero; ``asc`` = más antiguo primero.
    """
    folder = _safe_folder_path(maildir_root, folder_id)
    cur = folder / "cur"
    new = folder / "new"
    raw: list[tuple[int, Path]] = []
    for d in (cur, new):
        if not d.is_dir():
            continue
        for p in d.iterdir():
            if p.is_file():
                try:
                    st = p.stat()
                    raw.append((st.st_mtime_ns, p))
                except OSError:
                    continue

    lim = max(1, min(limit, 500))
    off = max(0, offset)
    qn = (q or "").strip().lower()
    use_header_sort = (sort_by or "").strip().lower() == "header_date"
    asc = (sort_order or "").strip().lower() == "asc"

    header_meta: dict[Path, tuple[str, str, str | None]] = {}
    if use_header_sort:
        rows = _collect_header_rows_parallel(raw)
        if asc:
            rows.sort(key=lambda r: (r[0], r[1]))
        else:
            rows.sort(key=lambda r: (-r[0], -r[1]))
        ordered = [(r[1], r[2]) for r in rows]
        header_meta = {r[2]: (r[3], r[4], r[5]) for r in rows}
    else:
        if asc:
            raw.sort(key=lambda x: x[0])
        else:
            raw.sort(key=lambda x: -x[0])
        ordered = raw

    if not qn:
        slice_paths = ordered[off : off + lim]
    else:
        matches: list[tuple[int, Path]] = []
        for mtime_ns, p in ordered:
            if p in header_meta:
                subject, from_, _d = header_meta[p]
            else:
                try:
                    subject, from_, _d = _headers_from_file(p)
                except OSError:
                    continue
            if not _maildir_matches_query(subject or "", from_ or "", qn):
                continue
            matches.append((mtime_ns, p))
        slice_paths = matches[off : off + lim]

    out: list[MessageListItem] = []
    for _mt, path in slice_paths:
        if path in header_meta:
            subject, from_, date = header_meta[path]
        else:
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
class MessageAttachment:
    """Índice de parte hoja en ``walk()`` (solo nodos no-multipart), estable entre lecturas."""

    leaf_index: int
    filename: str | None
    content_type: str
    size: int
    disposition: str | None
    content_id: str | None


@dataclass
class MessageBody:
    key: str
    subject: str
    from_addr: str
    date_display: str | None
    text_plain: str | None
    text_html: str | None
    attachments: list[MessageAttachment]


def _normalize_content_id(raw: str | None) -> str | None:
    if not raw:
        return None
    s = raw.strip()
    if s.startswith("<") and s.endswith(">"):
        s = s[1:-1]
    s = s.strip()
    return s or None


def _disposition_main(part: email.message.Message) -> str:
    cd = part.get("Content-Disposition")
    if not cd:
        return ""
    try:
        main = str(cd).split(";", 1)[0].strip().lower()
        return main
    except Exception:
        return ""


def _cid_lookup(uri: str, cid_map: dict[str, str]) -> str | None:
    if uri in cid_map:
        return cid_map[uri]
    base = uri.split("@", 1)[0]
    if base != uri and base in cid_map:
        return cid_map[base]
    ulow = uri.lower()
    for k, v in cid_map.items():
        if k.lower() == ulow:
            return v
        if k.split("@", 1)[0].lower() == ulow.split("@", 1)[0]:
            return v
    return None


def _rewrite_html_cids(html: str, cid_map: dict[str, str]) -> str:
    if not html or not cid_map:
        return html

    def repl(m: re.Match[str]) -> str:
        ref = m.group(1)
        u = _cid_lookup(ref, cid_map)
        return u if u is not None else m.group(0)

    return _CID_SRC_RE.sub(repl, html)


def _extract_body_and_attachments(
    msg: email.message.Message,
) -> tuple[str | None, str | None, list[MessageAttachment], dict[str, str]]:
    plain_parts: list[str] = []
    html_parts: list[str] = []
    attachments: list[MessageAttachment] = []
    cid_map: dict[str, str] = {}
    leaf_idx = 0

    if msg.is_multipart():
        for part in msg.walk():
            if part.is_multipart():
                continue
            ctype = (part.get_content_type() or "application/octet-stream").lower()
            disp_m = _disposition_main(part)
            fname = part.get_filename()
            cid_raw = _normalize_content_id(part.get("Content-ID"))
            try:
                raw = part.get_payload(decode=True)
            except Exception:
                leaf_idx += 1
                continue
            if raw is None:
                leaf_idx += 1
                continue

            is_body_plain = ctype == "text/plain" and not fname and disp_m != "attachment"
            is_body_html = ctype == "text/html" and not fname and disp_m != "attachment"

            if is_body_plain:
                try:
                    charset = part.get_content_charset() or "utf-8"
                    plain_parts.append(raw.decode(charset, errors="replace"))
                except Exception:
                    pass
                leaf_idx += 1
                continue
            if is_body_html:
                try:
                    charset = part.get_content_charset() or "utf-8"
                    html_parts.append(raw.decode(charset, errors="replace"))
                except Exception:
                    pass
                leaf_idx += 1
                continue

            if cid_raw and ctype.startswith("image/") and disp_m != "attachment":
                if 0 < len(raw) <= _MAX_INLINE_IMAGE_BYTES:
                    b64 = base64.b64encode(raw).decode("ascii")
                    data_uri = f"data:{ctype};base64,{b64}"
                    cid_map[cid_raw] = data_uri
                    base = cid_raw.split("@", 1)[0]
                    if base != cid_raw:
                        cid_map.setdefault(base, data_uri)
                    leaf_idx += 1
                    continue
                # Imagen inline demasiado grande para data: URI: se ofrece como adjunto.

            if disp_m == "attachment" or fname or ctype not in ("text/plain", "text/html"):
                dec_fn: str | None = fname
                if dec_fn:
                    try:
                        dec_fn = str(make_header(decode_header(dec_fn)))
                    except Exception:
                        pass
                attachments.append(
                    MessageAttachment(
                        leaf_index=leaf_idx,
                        filename=dec_fn,
                        content_type=ctype,
                        size=len(raw),
                        disposition=disp_m or None,
                        content_id=cid_raw,
                    )
                )
            leaf_idx += 1
    else:
        ctype = (msg.get_content_type() or "").lower()
        disp_m = _disposition_main(msg)
        fname = msg.get_filename()
        try:
            raw = msg.get_payload(decode=True)
            if raw:
                charset = msg.get_content_charset() or "utf-8"
                text = raw.decode(charset, errors="replace")
                if ctype == "text/html" and not fname and disp_m != "attachment":
                    html_parts.append(text)
                elif ctype == "text/plain" and not fname and disp_m != "attachment":
                    plain_parts.append(text)
                elif disp_m == "attachment" or fname or ctype not in ("text/plain", "text/html"):
                    dec_fn: str | None = fname
                    if dec_fn:
                        try:
                            dec_fn = str(make_header(decode_header(dec_fn)))
                        except Exception:
                            pass
                    attachments.append(
                        MessageAttachment(
                            leaf_index=0,
                            filename=dec_fn,
                            content_type=ctype,
                            size=len(raw),
                            disposition=disp_m or None,
                            content_id=_normalize_content_id(msg.get("Content-ID")),
                        )
                    )
        except Exception:
            pass

    pl = "\n\n".join(plain_parts).strip() or None
    hl_raw = "\n<hr>\n".join(html_parts).strip() or None
    hl = _rewrite_html_cids(hl_raw, cid_map) if hl_raw else None
    return pl, hl, attachments, cid_map


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
            tpl, thtml, attachments, _ = _extract_body_and_attachments(msg)
            return MessageBody(
                key=key,
                subject=subject,
                from_addr=from_,
                date_display=date,
                text_plain=tpl,
                text_html=thtml,
                attachments=attachments,
            )
    raise FileNotFoundError("message_not_found")


def read_message_leaf_bytes(
    maildir_root: Path,
    *,
    folder_id: str,
    message_key: str,
    leaf_index: int,
) -> tuple[bytes, str | None, str]:
    """Devuelve ``(payload, filename, content_type)`` para la parte hoja ``leaf_index``."""
    folder = _safe_folder_path(maildir_root, folder_id)
    key = message_key.strip()
    if not key or "/" in key or key == "." or ".." in key:
        raise ValueError("invalid_message_key")
    if leaf_index < 0:
        raise ValueError("invalid_leaf_index")
    for sub in ("cur", "new"):
        path = folder / sub / key
        if not path.is_file():
            continue
        raw = path.read_bytes()
        msg = BytesParser(policy=compat32).parsebytes(raw)
        i = 0
        for part in msg.walk():
            if part.is_multipart():
                continue
            if i == leaf_index:
                try:
                    payload = part.get_payload(decode=True) or b""
                except Exception as exc:
                    raise ValueError("part_decode_error") from exc
                fn = part.get_filename()
                if fn:
                    try:
                        fn = str(make_header(decode_header(fn)))
                    except Exception:
                        pass
                ctype = part.get_content_type() or "application/octet-stream"
                return payload, fn, ctype
            i += 1
        raise ValueError("leaf_index_out_of_range")
    raise FileNotFoundError("message_not_found")
