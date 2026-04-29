"""Tests for Maildir browser (local paths only)."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services.mailbox_browser_service import list_maildir_folders, list_messages, read_message


def _write_msg(cur: Path, name: str, raw: bytes) -> None:
    cur.mkdir(parents=True, exist_ok=True)
    (cur / name).write_bytes(raw)


def test_inbox_folder_and_list(tmp_path: Path) -> None:
    root = tmp_path / "Maildir"
    _write_msg(
        root / "cur",
        "abc.host:2,S",
        b"Subject: Hola\nFrom: a@b.com\nDate: Mon, 1 Jan 2024 12:00:00 +0000\n\nbody\n",
    )
    for d in ("new", "tmp"):
        (root / d).mkdir(parents=True, exist_ok=True)

    folders = list_maildir_folders(root)
    assert ("INBOX", "Bandeja de entrada") in folders

    msgs = list_messages(root, folder_id="INBOX", limit=10, offset=0)
    assert len(msgs) == 1
    assert msgs[0].subject == "Hola"


def test_subfolder(tmp_path: Path) -> None:
    root = tmp_path / "Maildir"
    sent = root / ".Sent"
    _write_msg(
        sent / "cur",
        "x.host:2,S",
        b"Subject: Out\nFrom: me@test.com\n\nok\n",
    )
    for sub in (sent / "new", sent / "tmp"):
        sub.mkdir(parents=True, exist_ok=True)

    folders = list_maildir_folders(root)
    assert any(f[0] == ".Sent" for f in folders)
    sent_entry = next(f for f in folders if f[0] == ".Sent")
    assert sent_entry[1] == "Enviados"

    msgs = list_messages(root, folder_id=".Sent", limit=5, offset=0)
    assert len(msgs) == 1
    assert msgs[0].subject == "Out"


def test_read_message_plain(tmp_path: Path) -> None:
    root = tmp_path / "Maildir"
    key = "k.host:2,S"
    _write_msg(
        root / "cur",
        key,
        b"Subject: Full\nFrom: u@x.com\n\nhello world",
    )
    (root / "new").mkdir()
    (root / "tmp").mkdir()

    m = read_message(root, folder_id="INBOX", message_key=key)
    assert m.subject == "Full"
    assert m.text_plain and "hello world" in m.text_plain


def test_rejects_path_traversal(tmp_path: Path) -> None:
    root = tmp_path / "Maildir"
    (root / "cur").mkdir(parents=True)
    (root / "new").mkdir()
    (root / "tmp").mkdir()

    with pytest.raises(ValueError):
        list_messages(root, folder_id="..", limit=1, offset=0)


def test_new_only_subfolder_is_listed(tmp_path: Path) -> None:
    root = tmp_path / "Maildir"
    for sub in ("cur", "new", "tmp"):
        (root / sub).mkdir(parents=True)
    sent = root / ".Sent"
    (sent / "new").mkdir(parents=True)
    (sent / "tmp").mkdir(parents=True)

    folders = list_maildir_folders(root)
    assert any(f[0] == ".Sent" for f in folders)


def test_standard_gmail_folders_created_when_absent(tmp_path: Path) -> None:
    root = tmp_path / "Maildir"
    for sub in ("cur", "new", "tmp"):
        (root / sub).mkdir(parents=True)

    folders = {fid: name for fid, name in list_maildir_folders(root)}
    assert ".SENT" in folders and folders[".SENT"] == "Enviados"
    assert ".DRAFT" in folders and folders[".DRAFT"] == "Borradores"
    assert ".SPAM" in folders
    assert (root / ".SENT" / "cur").is_dir()
