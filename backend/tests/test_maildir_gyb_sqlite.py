"""Import Maildir desde export GYB usando msg-db.sqlite (etiquetas fuera de cabeceras)."""
from __future__ import annotations

import sqlite3

from pathlib import Path

from app.services.mailbox_browser_service import list_maildir_folders
from app.services.maildir_service import import_mbox_tree_to_maildir


def _write_gyb_with_sqlite(tmp: Path) -> tuple[Path, Path]:
    """Árbol GYB mínimo + ``msg-db.sqlite`` con dos etiquetas por mensaje."""
    root = tmp / "gyb_export"
    eml = root / "2024" / "1" / "15" / "msgid123.eml"
    eml.parent.mkdir(parents=True)
    eml.write_bytes(b"Subject: Solo sqlite\nFrom: a@b.com\n\nhi\n")
    db = root / "msg-db.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE messages (
            message_num INTEGER PRIMARY KEY,
            message_filename TEXT,
            message_internaldate TIMESTAMP
        );
        CREATE TABLE labels (message_num INTEGER, label TEXT);
        CREATE TABLE uids (message_num INTEGER, uid TEXT PRIMARY KEY);
        CREATE UNIQUE INDEX labelidx ON labels (message_num, label);
        """
    )
    conn.execute(
        "INSERT INTO messages (message_filename, message_internaldate) VALUES (?, ?)",
        ("2024/1/15/msgid123.eml", "2024-01-15 00:00:00"),
    )
    mid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    for lab in ("SENT", "Proyectos/Code"):
        conn.execute("INSERT INTO labels (message_num, label) VALUES (?, ?)", (mid, lab))
    conn.commit()
    conn.close()
    mdir = tmp / "Maildir"
    return root, mdir


def test_gyb_sqlite_creates_maildir_subfolders(tmp_path: Path) -> None:
    gyb, mdir = _write_gyb_with_sqlite(tmp_path)
    stats = import_mbox_tree_to_maildir(mbox_root=gyb, maildir_root=mdir)
    assert stats.messages == 1
    assert stats.eml_files == 1
    folders = {fid for fid, _ in list_maildir_folders(mdir)}
    assert ".SENT" in folders
    assert ".Proyectos_Code" in folders


def test_header_labels_when_no_sqlite_row(tmp_path: Path) -> None:
    root = tmp_path / "gyb"
    eml = root / "2024" / "2" / "1" / "orphan.eml"
    eml.parent.mkdir(parents=True)
    eml.write_bytes(
        b"Subject: Headers\nX-Gmail-Labels: Inbox,MyStuff\nFrom: u@v.com\n\nx\n"
    )
    db = root / "msg-db.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE messages (
            message_num INTEGER PRIMARY KEY,
            message_filename TEXT,
            message_internaldate TIMESTAMP
        );
        CREATE TABLE labels (message_num INTEGER, label TEXT);
        CREATE TABLE uids (message_num INTEGER, uid TEXT PRIMARY KEY);
        CREATE UNIQUE INDEX labelidx ON labels (message_num, label);
        """
    )
    conn.commit()
    conn.close()
    mdir = tmp_path / "Maildir"
    import_mbox_tree_to_maildir(mbox_root=root, maildir_root=mdir)
    folders = {fid for fid, _ in list_maildir_folders(mdir)}
    assert ".MyStuff" in folders
