"""Convert GYB `.mbox` exports into Maildir layouts served by Dovecot."""
from __future__ import annotations

import email.utils
import hashlib
import mailbox
import os
import re
import time
from dataclasses import dataclass
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
    """Crea cur/new/tmp; idempotente."""
    _maildir(maildir_root, create=True)


@dataclass(slots=True)
class MaildirImportStats:
    mbox_files: int = 0
    messages: int = 0
    folders: int = 0
    skipped_duplicates: int = 0


def _message_digest(raw: bytes) -> str:
    return hashlib.sha1(raw).hexdigest()


def import_mbox_tree_to_maildir(
    *,
    mbox_root: Path,
    maildir_root: Path,
) -> MaildirImportStats:
    """Walk the GYB folder tree and merge every `.mbox` into a Maildir layout.

    GYB stores messages under `messages/` in one or more `.mbox` files plus a
    sqlite index. We ignore the sqlite index and replay the mbox payloads,
    turning Gmail labels into Maildir sub-folders.
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
            digest = _message_digest(raw)
            if digest in seen:
                stats.skipped_duplicates += 1
                continue
            seen.add(digest)

            labels = msg.get("X-Gmail-Labels") or msg.get("X-GMAIL-LABELS") or ""
            targets: list[mailbox.Maildir] = [default]
            if labels:
                for label in [l.strip() for l in labels.split(",") if l.strip()]:
                    folder = _safe_folder(label)
                    sub_path = maildir_root / f".{folder}"
                    targets.append(_maildir(sub_path))
                    stats.folders += 1
            for md in targets:
                md.add(msg)
            stats.messages += 1

    return stats
