"""Lectura segura del export GYB local (archivos ``.eml`` bajo ``/var/msa/work/gmail/<email>``)."""
from __future__ import annotations

import base64
import email
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from email.header import decode_header, make_header
from email.parser import BytesParser
from email.policy import compat32
from email.utils import parsedate_to_datetime
from pathlib import Path

from app.services.mailbox_browser_service import (
    MessageBody,
    _decode_mime_header,
    _extract_body_and_attachments,
)
from app.services.maildir_service import _normalize_gyb_relative_path

# Etiquetas de sistema Gmail → título en español (las personalizadas se muestran tal cual).
GMAIL_LABEL_DISPLAY_ES: dict[str, str] = {
    "INBOX": "Bandeja de entrada",
    "SENT": "Enviados",
    "DRAFT": "Borradores",
    "TRASH": "Papelera",
    "SPAM": "Correo no deseado",
    "STARRED": "Destacados",
    "IMPORTANT": "Importante",
    "CHAT": "Chat",
    "UNREAD": "No leídos",
    "SNOOZED": "Pospuestos",
    "CATEGORY_PERSONAL": "Principal",
    "CATEGORY_SOCIAL": "Social",
    "CATEGORY_PROMOTIONS": "Promociones",
    "CATEGORY_UPDATES": "Actualizaciones",
    "CATEGORY_FORUMS": "Foros",
}


def gyb_gmail_label_display_name(label: str) -> str:
    lab = (label or "").strip()
    if not lab:
        return lab
    mapped = GMAIL_LABEL_DISPLAY_ES.get(lab)
    if mapped:
        return mapped
    up = lab.upper()
    mapped = GMAIL_LABEL_DISPLAY_ES.get(up)
    if mapped:
        return mapped
    return lab


def resolve_gyb_list_folder(work_root: Path, folder_id: str) -> Path:
    """Resuelve ``folder_id`` (ruta relativa bajo work root) a directorio.

    ``folder_id`` vacío = raíz del trabajo GYB.
    """
    wr = work_root.resolve()
    raw = (folder_id or "").strip().replace("\\", "/").strip("/")
    if ".." in raw.split("/"):
        raise ValueError("invalid_folder")
    target = wr if not raw else (wr / raw).resolve()
    try:
        target.relative_to(wr)
    except ValueError as exc:
        raise ValueError("invalid_folder") from exc
    return target


@dataclass
class GybWorkFolder:
    """Entrada de panel lateral: carpeta en disco o etiqueta Gmail."""

    folder_id: str
    display_name: str


def list_gyb_work_folders(work_root: Path) -> list[GybWorkFolder]:
    if not work_root.is_dir():
        return []
    wr = work_root.resolve()
    seen: set[str] = set()
    try:
        for p in work_root.rglob("*.eml"):
            if not p.is_file():
                continue
            parent = p.parent.resolve()
            if parent == wr:
                seen.add("")
            else:
                try:
                    rel = parent.relative_to(wr)
                except ValueError:
                    continue
                seen.add(rel.as_posix())
    except OSError:
        return []

    def sort_key(fid: str) -> tuple[int, str]:
        return (0 if fid == "" else 1, fid.lower())

    out: list[GybWorkFolder] = []
    for fid in sorted(seen, key=sort_key):
        name = "(raíz)" if fid == "" else fid.replace("/", " / ")
        out.append(GybWorkFolder(folder_id=fid, display_name=name))
    return out


def _gyb_sqlite_uri(work_root: Path) -> str | None:
    db = (work_root / "msg-db.sqlite").resolve()
    if not db.is_file():
        return None
    return f"file:{db.as_posix()}?mode=ro"


def list_gyb_gmail_label_folders(work_root: Path) -> list[GybWorkFolder]:
    """Etiquetas distintas en ``msg-db.sqlite`` (mismo origen que la importación a Maildir)."""
    uri = _gyb_sqlite_uri(work_root)
    if uri is None:
        return []
    conn = sqlite3.connect(uri, uri=True)
    try:
        cur = conn.execute(
            """
            SELECT DISTINCT label FROM labels
            WHERE label IS NOT NULL AND trim(label) != ''
            ORDER BY label COLLATE NOCASE
            """
        )
        rows = [r[0] for r in cur.fetchall() if r[0]]
    finally:
        conn.close()
    priority: dict[str, int] = {
        "INBOX": 0,
        "STARRED": 1,
        "IMPORTANT": 2,
        "SENT": 3,
        "DRAFT": 4,
        "SPAM": 5,
        "TRASH": 6,
        "CHAT": 7,
        "CATEGORY_PERSONAL": 10,
        "CATEGORY_SOCIAL": 11,
        "CATEGORY_PROMOTIONS": 12,
        "CATEGORY_UPDATES": 13,
        "CATEGORY_FORUMS": 14,
    }

    def _label_row_sort_key(lab: str) -> tuple[int, str]:
        return (priority.get(lab.upper(), 100), lab.lower())

    rows = sorted(rows, key=_label_row_sort_key)
    return [GybWorkFolder(folder_id=lab, display_name=gyb_gmail_label_display_name(lab)) for lab in rows]


def encode_eml_rel_key(rel: Path) -> str:
    raw = rel.as_posix().encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_eml_path(work_root: Path, key: str) -> Path:
    """Resuelve ``key`` a ruta ``.eml`` bajo ``work_root`` (sin traversal)."""
    key = (key or "").strip()
    if not key:
        raise ValueError("invalid_key")
    pad = "=" * ((4 - len(key) % 4) % 4)
    try:
        rel_s = base64.urlsafe_b64decode(key + pad).decode("utf-8")
    except Exception as exc:
        raise ValueError("invalid_key") from exc
    if not rel_s or rel_s.startswith("/") or ".." in rel_s.split("/"):
        raise ValueError("invalid_key")
    wr = work_root.resolve()
    target = (wr / rel_s).resolve()
    try:
        target.relative_to(wr)
    except ValueError as exc:
        raise ValueError("invalid_key") from exc
    if target.suffix.lower() != ".eml":
        raise ValueError("not_eml")
    if not target.is_file():
        raise FileNotFoundError("eml_not_found")
    return target


def _headers_from_eml(path: Path, max_bytes: int = 96_000) -> tuple[str, str, str | None]:
    data = path.read_bytes()[:max_bytes]
    msg = email.message_from_bytes(data, policy=compat32)
    subject = _decode_mime_header(msg.get("Subject")) or "(sin asunto)"
    from_ = _decode_mime_header(msg.get("From")) or "—"
    date = msg.get("Date")
    return subject, from_, date


@dataclass
class GybEmlSummary:
    key: str
    subject: str
    from_addr: str
    date_display: str | None
    size: int
    labels: list[str] | None = None


@dataclass
class GybEmlPage:
    items: list[GybEmlSummary]
    has_more: bool
    total_in_scope: int
    total_matches: int


def _path_to_summary(
    path: Path, wr: Path, labels: list[str] | None = None
) -> GybEmlSummary | None:
    try:
        rel = path.resolve().relative_to(wr)
    except ValueError:
        return None
    k = encode_eml_rel_key(rel)
    try:
        subj, from_, date = _headers_from_eml(path)
    except OSError:
        return None
    try:
        sz = path.stat().st_size
    except OSError:
        sz = 0
    tag_list: list[str] | None = list(labels) if labels else None
    return GybEmlSummary(
        key=k,
        subject=subj,
        from_addr=from_,
        date_display=date,
        size=sz,
        labels=tag_list,
    )


def _messages_has_internaldate(uri: str) -> bool:
    conn = sqlite3.connect(uri, uri=True)
    try:
        cur = conn.execute("PRAGMA table_info(messages)")
        return any(str(row[1]).lower() == "message_internaldate" for row in cur.fetchall())
    finally:
        conn.close()


def _parse_msgdb_internaldate_to_ns(val: object | None) -> int | None:
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    try:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
            try:
                dt = datetime.strptime(s[:26], fmt).replace(tzinfo=timezone.utc)
                return int(dt.timestamp() * 1_000_000_000)
            except ValueError:
                continue
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1_000_000_000)
    except (ValueError, TypeError, OSError, OverflowError):
        return None


def _msgdb_rows_for_scope(
    work_root: Path, label: str, list_scope: str
) -> dict[str, int | None]:
    """relpath normalizado → mejor ``message_internaldate`` en ns (o None)."""
    uri = _gyb_sqlite_uri(work_root)
    if uri is None:
        return {}
    has_id = _messages_has_internaldate(uri)
    id_col = "m.message_internaldate" if has_id else "NULL"
    conn = sqlite3.connect(uri, uri=True)
    try:
        if list_scope == "all":
            cur = conn.execute(
                f"SELECT m.message_filename, {id_col} FROM messages AS m"
            )
        else:
            cur = conn.execute(
                f"""
                SELECT m.message_filename, {id_col}
                FROM messages AS m
                INNER JOIN labels AS l ON l.message_num = m.message_num
                WHERE l.label = ?
                """,
                (label,),
            )
        best: dict[str, int | None] = {}
        for fn, raw_id in cur.fetchall():
            nk = _normalize_gyb_relative_path(fn or "")
            if not nk:
                continue
            ns = _parse_msgdb_internaldate_to_ns(raw_id) if has_id else None
            if nk not in best:
                best[nk] = ns
            elif ns is not None and (best[nk] is None or ns > best[nk]):
                best[nk] = ns
        return best
    finally:
        conn.close()


def _load_labels_by_relpath(work_root: Path) -> dict[str, list[str]]:
    uri = _gyb_sqlite_uri(work_root)
    if uri is None:
        return {}
    conn = sqlite3.connect(uri, uri=True)
    try:
        cur = conn.execute(
            """
            SELECT m.message_filename, l.label
            FROM messages AS m
            INNER JOIN labels AS l ON l.message_num = m.message_num
            """
        )
        acc: dict[str, list[str]] = {}
        for fn, lab in cur.fetchall():
            if not fn or not lab:
                continue
            nk = _normalize_gyb_relative_path(fn or "")
            if not nk:
                continue
            b = acc.setdefault(nk, [])
            if lab not in b:
                b.append(lab)
        for k in acc:
            acc[k].sort(key=str.lower)
        return acc
    finally:
        conn.close()


def _path_matches_search(path: Path, q_lower: str) -> bool:
    if not q_lower:
        return True
    try:
        data = path.read_bytes()[:96_000]
        msg = email.message_from_bytes(data, policy=compat32)
        blob_parts: list[str] = []
        for h in (
            "Subject",
            "From",
            "To",
            "Cc",
            "Bcc",
            "Reply-To",
            "Sender",
            "Delivered-To",
        ):
            v = msg.get(h)
            if v:
                blob_parts.append(_decode_mime_header(v))
        for h in ("Message-ID", "References", "In-Reply-To"):
            v = msg.get(h)
            if v:
                blob_parts.append(str(v))
        for part in msg.walk():
            if part.is_multipart():
                continue
            fn = part.get_filename()
            if fn:
                try:
                    fn = str(make_header(decode_header(fn)))
                except Exception:
                    fn = str(fn)
                blob_parts.append(fn)
        blob = " ".join(blob_parts).lower()
        if q_lower in blob:
            return True
        if msg.is_multipart():
            for part in msg.walk():
                if part.is_multipart() or part.get_content_type() != "text/plain":
                    continue
                try:
                    pl = part.get_payload(decode=True)
                    if isinstance(pl, bytes):
                        t = pl.decode("utf-8", errors="ignore")[:8000]
                    else:
                        t = str(pl)[:8000]
                    if q_lower in t.lower():
                        return True
                except Exception:
                    continue
                break
        else:
            try:
                pl = msg.get_payload(decode=True)
                if isinstance(pl, bytes):
                    t = pl.decode("utf-8", errors="ignore")[:8000]
                else:
                    t = str(pl)[:8000]
                if q_lower in t.lower():
                    return True
            except Exception:
                pass
        return False
    except OSError:
        return False


def _email_date_sort_key_ns(date_hdr: str | None, fallback_mtime_ns: int) -> int:
    if date_hdr:
        try:
            dt = parsedate_to_datetime(date_hdr)
            if dt is not None:
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return int(dt.timestamp() * 1_000_000_000)
        except (TypeError, ValueError, OSError, OverflowError):
            pass
    return fallback_mtime_ns


def _sort_entries_by_keys(
    entries: list[tuple[Path, int | None]],
    sort_by: str,
    sort_order: str,
) -> list[Path]:
    rows: list[tuple[int, int, Path]] = []
    for p, id_ns in entries:
        try:
            mtime_ns = p.stat().st_mtime_ns
        except OSError:
            continue
        if sort_by == "mtime":
            sk = mtime_ns
        else:
            if id_ns is not None:
                sk = id_ns
            else:
                try:
                    _, _, date_hdr = _headers_from_eml(p)
                except OSError:
                    date_hdr = None
                sk = _email_date_sort_key_ns(date_hdr, mtime_ns)
        rows.append((sk, mtime_ns, p))
    rev = sort_order != "asc"
    rows.sort(key=lambda t: (t[0], t[1]), reverse=rev)
    return [t[2] for t in rows]


def _collect_disk_eml_paths(work_root: Path, folder_id: str, list_scope: str) -> list[Path]:
    wr = work_root.resolve()
    if not wr.is_dir():
        return []
    if list_scope == "all":
        return [p for p in wr.rglob("*.eml") if p.is_file()]
    try:
        folder = resolve_gyb_list_folder(work_root, folder_id)
    except ValueError:
        return []
    if not folder.is_dir():
        return []
    return [p for p in folder.glob("*.eml") if p.is_file()]


def _collect_label_path_entries(
    work_root: Path, label: str, list_scope: str
) -> list[tuple[Path, int | None]]:
    wr = work_root.resolve()
    if list_scope == "all":
        rowmap = _msgdb_rows_for_scope(work_root, "", "all")
    else:
        lab = (label or "").strip()
        if not lab:
            return []
        rowmap = _msgdb_rows_for_scope(work_root, lab, "folder")
    out: list[tuple[Path, int | None]] = []
    for nk, id_ns in rowmap.items():
        p = (wr / nk).resolve()
        try:
            p.relative_to(wr)
        except ValueError:
            continue
        if p.is_file() and p.suffix.lower() == ".eml":
            out.append((p, id_ns))
    return out


def list_gyb_eml_page_from_entries(
    work_root: Path,
    entries: list[tuple[Path, int | None]],
    *,
    limit: int,
    offset: int,
    q: str | None,
    sort_by: str,
    sort_order: str,
    labels_by_relpath: dict[str, list[str]] | None,
) -> GybEmlPage:
    wr = work_root.resolve()
    qn = (q or "").strip().lower()
    lim = max(1, min(limit, 200))
    off = max(0, offset)
    sb = sort_by if sort_by in ("mtime", "header_date") else "header_date"
    so = sort_order if sort_order in ("asc", "desc") else "desc"
    total_in_scope = len(entries)
    sorted_paths = _sort_entries_by_keys(entries, sb, so)
    if qn:
        filtered = [p for p in sorted_paths if _path_matches_search(p, qn)]
        total_matches = len(filtered)
        slice_paths = filtered[off : off + lim]
    else:
        total_matches = total_in_scope
        slice_paths = sorted_paths[off : off + lim]
    has_more = off + len(slice_paths) < total_matches
    items: list[GybEmlSummary] = []
    for path in slice_paths:
        rel_s: str | None = None
        try:
            rel_s = path.resolve().relative_to(wr).as_posix()
        except ValueError:
            pass
        tags = (
            labels_by_relpath.get(rel_s, [])
            if (labels_by_relpath and rel_s)
            else None
        )
        s = _path_to_summary(path, wr, labels=tags)
        if s:
            items.append(s)
    return GybEmlPage(
        items=items,
        has_more=has_more,
        total_in_scope=total_in_scope,
        total_matches=total_matches,
    )


def list_gyb_eml_summaries(
    work_root: Path,
    *,
    folder_id: str = "",
    limit: int = 80,
    offset: int = 0,
    q: str | None = None,
    list_scope: str = "folder",
    sort_by: str = "header_date",
    sort_order: str = "desc",
) -> GybEmlPage:
    if not work_root.is_dir():
        return GybEmlPage(items=[], has_more=False, total_in_scope=0, total_matches=0)
    paths = _collect_disk_eml_paths(work_root, folder_id, list_scope)
    entries = [(p, None) for p in paths]
    return list_gyb_eml_page_from_entries(
        work_root,
        entries,
        limit=limit,
        offset=offset,
        q=q,
        sort_by=sort_by,
        sort_order=sort_order,
        labels_by_relpath=None,
    )


def list_gyb_eml_summaries_for_label(
    work_root: Path,
    *,
    label: str,
    limit: int = 80,
    offset: int = 0,
    q: str | None = None,
    list_scope: str = "folder",
    sort_by: str = "header_date",
    sort_order: str = "desc",
) -> GybEmlPage:
    if not work_root.is_dir():
        return GybEmlPage(items=[], has_more=False, total_in_scope=0, total_matches=0)
    if list_scope != "all":
        lab = (label or "").strip()
        if not lab:
            return GybEmlPage(items=[], has_more=False, total_in_scope=0, total_matches=0)
    entries = _collect_label_path_entries(work_root, label, list_scope)
    labels_map = (
        _load_labels_by_relpath(work_root) if _gyb_sqlite_uri(work_root) else None
    )
    return list_gyb_eml_page_from_entries(
        work_root,
        entries,
        limit=limit,
        offset=offset,
        q=q,
        sort_by=sort_by,
        sort_order=sort_order,
        labels_by_relpath=labels_map,
    )


def read_gyb_eml_message(work_root: Path, *, key: str) -> MessageBody:
    path = decode_eml_path(work_root, key)
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


def read_gyb_eml_leaf_bytes(path: Path, *, leaf_index: int) -> tuple[bytes, str | None, str]:
    if leaf_index < 0:
        raise ValueError("invalid_leaf_index")
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
                    fn = str(fn)
            ctype = part.get_content_type() or "application/octet-stream"
            return payload, fn, ctype
        i += 1
    raise ValueError("leaf_index_out_of_range")
