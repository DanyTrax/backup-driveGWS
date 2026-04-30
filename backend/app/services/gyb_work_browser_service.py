"""Lectura segura del export GYB local (archivos ``.eml`` bajo ``/var/msa/work/gmail/<email>``)."""
from __future__ import annotations

import base64
import email
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


def list_gyb_eml_summaries(
    work_root: Path,
    *,
    limit: int = 80,
    offset: int = 0,
) -> list[GybEmlSummary]:
    if not work_root.is_dir():
        return []
    wr = work_root.resolve()
    files: list[tuple[int, Path]] = []
    try:
        for p in work_root.rglob("*.eml"):
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
    slice_ = files[offset : offset + lim]
    out: list[GybEmlSummary] = []
    for _mt, path in slice_:
        try:
            rel = path.resolve().relative_to(wr)
        except ValueError:
            continue
        k = encode_eml_rel_key(rel)
        try:
            subj, from_, date = _headers_from_eml(path)
        except OSError:
            continue
        try:
            sz = path.stat().st_size
        except OSError:
            sz = 0
        out.append(
            GybEmlSummary(
                key=k,
                subject=subj,
                from_addr=from_,
                date_display=date,
                size=sz,
            )
        )
    return out


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
