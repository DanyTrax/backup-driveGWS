"""Lectura segura del export GYB local (archivos ``.eml`` bajo ``/var/msa/work/gmail/<email>``)."""
from __future__ import annotations

import base64
import email
import sqlite3
from dataclasses import dataclass
from email.header import decode_header, make_header
from email.parser import BytesParser
from email.policy import compat32
from pathlib import Path

from app.services.mailbox_browser_service import (
    MessageBody,
    _decode_mime_header,
    _extract_body_and_attachments,
)
from app.services.maildir_service import _normalize_gyb_relative_path


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
    return [GybWorkFolder(folder_id=lab, display_name=lab) for lab in rows]


def _relpaths_for_gmail_label(work_root: Path, label: str) -> list[str]:
    uri = _gyb_sqlite_uri(work_root)
    if uri is None:
        return []
    conn = sqlite3.connect(uri, uri=True)
    try:
        cur = conn.execute(
            """
            SELECT DISTINCT m.message_filename
            FROM messages AS m
            INNER JOIN labels AS l ON l.message_num = m.message_num
            WHERE l.label = ?
            """,
            (label,),
        )
        ordered: list[str] = []
        seen: set[str] = set()
        for (fn,) in cur.fetchall():
            nk = _normalize_gyb_relative_path(fn or "")
            if nk and nk not in seen:
                seen.add(nk)
                ordered.append(nk)
        return ordered
    finally:
        conn.close()


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


def _summary_matches_query(subject: str, from_addr: str, q_lower: str) -> bool:
    if not q_lower:
        return True
    return q_lower in subject.lower() or q_lower in from_addr.lower()


def _path_to_summary(path: Path, wr: Path) -> GybEmlSummary | None:
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
    return GybEmlSummary(
        key=k,
        subject=subj,
        from_addr=from_,
        date_display=date,
        size=sz,
    )


@dataclass
class GybEmlSummary:
    key: str
    subject: str
    from_addr: str
    date_display: str | None
    size: int


def list_gyb_eml_summaries(
    work_root: Path,
    *,
    folder_id: str = "",
    limit: int = 80,
    offset: int = 0,
    q: str | None = None,
) -> list[GybEmlSummary]:
    if not work_root.is_dir():
        return []
    folder = resolve_gyb_list_folder(work_root, folder_id)
    if not folder.is_dir():
        return []
    wr = work_root.resolve()
    qn = (q or "").strip().lower()
    files: list[tuple[int, Path]] = []
    try:
        for p in folder.glob("*.eml"):
            if p.is_file():
                try:
                    st = p.stat()
                    files.append((st.st_mtime_ns, p))
                except OSError:
                    continue
    except OSError:
        return []
    files.sort(key=lambda x: -x[0])
    lim = max(1, min(limit, 200))
    off = max(0, offset)

    if not qn:
        slice_ = files[off : off + lim]
        out: list[GybEmlSummary] = []
        for _mt, path in slice_:
            s = _path_to_summary(path, wr)
            if s:
                out.append(s)
        return out

    matches: list[GybEmlSummary] = []
    for _mt, path in files:
        try:
            subj, from_, date = _headers_from_eml(path)
        except OSError:
            continue
        if not _summary_matches_query(subj, from_, qn):
            continue
        try:
            sz = path.stat().st_size
        except OSError:
            sz = 0
        try:
            rel = path.resolve().relative_to(wr)
        except ValueError:
            continue
        matches.append(
            GybEmlSummary(
                key=encode_eml_rel_key(rel),
                subject=subj,
                from_addr=from_,
                date_display=date,
                size=sz,
            )
        )
    return matches[off : off + lim]


def list_gyb_eml_summaries_for_label(
    work_root: Path,
    *,
    label: str,
    limit: int = 80,
    offset: int = 0,
    q: str | None = None,
) -> list[GybEmlSummary]:
    lab = (label or "").strip()
    if not lab or not work_root.is_dir():
        return []
    wr = work_root.resolve()
    qn = (q or "").strip().lower()
    relpaths = _relpaths_for_gmail_label(work_root, lab)
    files: list[tuple[int, Path]] = []
    for rel in relpaths:
        p = (wr / rel).resolve()
        try:
            p.relative_to(wr)
        except ValueError:
            continue
        if not p.is_file() or p.suffix.lower() != ".eml":
            continue
        try:
            st = p.stat()
            files.append((st.st_mtime_ns, p))
        except OSError:
            continue
    files.sort(key=lambda x: -x[0])
    lim = max(1, min(limit, 200))
    off = max(0, offset)

    if not qn:
        slice_ = files[off : off + lim]
        out: list[GybEmlSummary] = []
        for _mt, path in slice_:
            s = _path_to_summary(path, wr)
            if s:
                out.append(s)
        return out

    matches: list[GybEmlSummary] = []
    for _mt, path in files:
        try:
            subj, from_, date = _headers_from_eml(path)
        except OSError:
            continue
        if not _summary_matches_query(subj, from_, qn):
            continue
        try:
            sz = path.stat().st_size
        except OSError:
            sz = 0
        try:
            rel = path.resolve().relative_to(wr)
        except ValueError:
            continue
        matches.append(
            GybEmlSummary(
                key=encode_eml_rel_key(rel),
                subject=subj,
                from_addr=from_,
                date_display=date,
                size=sz,
            )
        )
    return matches[off : off + lim]


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
