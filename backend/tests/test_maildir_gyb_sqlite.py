"""Import Maildir desde export GYB usando msg-db.sqlite (etiquetas fuera de cabeceras)."""
from __future__ import annotations

import sqlite3

from pathlib import Path

from app.services.mailbox_browser_service import list_maildir_folders, list_messages
from app.services.maildir_service import import_mbox_tree_to_maildir

_GYB_DB_SCHEMA = """
    CREATE TABLE messages (
        message_num INTEGER PRIMARY KEY,
        message_filename TEXT,
        message_internaldate TIMESTAMP
    );
    CREATE TABLE labels (message_num INTEGER, label TEXT);
    CREATE TABLE uids (message_num INTEGER, uid TEXT PRIMARY KEY);
    CREATE UNIQUE INDEX labelidx ON labels (message_num, label);
"""


def _write_gyb_with_sqlite(tmp: Path) -> tuple[Path, Path]:
    """Árbol GYB mínimo + ``msg-db.sqlite`` con dos etiquetas por mensaje."""
    root = tmp / "gyb_export"
    eml = root / "2024" / "1" / "15" / "msgid123.eml"
    eml.parent.mkdir(parents=True)
    eml.write_bytes(b"Subject: Solo sqlite\nFrom: a@b.com\n\nhi\n")
    db = root / "msg-db.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript(_GYB_DB_SCHEMA)
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


def test_incremental_import_skips_messages_already_in_maildir(tmp_path: Path) -> None:
    from app.services.maildir_service import _iter_maildir_message_files

    gyb, mdir = _write_gyb_with_sqlite(tmp_path)
    s1 = import_mbox_tree_to_maildir(mbox_root=gyb, maildir_root=mdir)
    assert s1.messages >= 1
    n1 = sum(1 for _ in _iter_maildir_message_files(mdir))
    s2 = import_mbox_tree_to_maildir(mbox_root=gyb, maildir_root=mdir)
    assert s2.messages == 0
    assert s2.skipped_duplicates >= 1
    n2 = sum(1 for _ in _iter_maildir_message_files(mdir))
    assert n2 == n1


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
    conn.executescript(_GYB_DB_SCHEMA)
    conn.commit()
    conn.close()
    mdir = tmp_path / "Maildir"
    import_mbox_tree_to_maildir(mbox_root=root, maildir_root=mdir)
    folders = {fid for fid, _ in list_maildir_folders(mdir)}
    assert ".MyStuff" in folders


def test_labels_from_sqlite_via_uid_when_path_wrong(tmp_path: Path) -> None:
    root = tmp_path / "gyb_export"
    eml = root / "2024" / "1" / "15" / "msgid888.eml"
    eml.parent.mkdir(parents=True)
    eml.write_bytes(b"Subject: Uid map\nFrom: a@b.com\n\nbody\n")
    conn = sqlite3.connect(root / "msg-db.sqlite")
    conn.executescript(_GYB_DB_SCHEMA)
    conn.execute(
        "INSERT INTO messages (message_filename, message_internaldate) VALUES (?, ?)",
        ("WRONG/PATH/msgid888.eml", "2024-01-15 00:00:00"),
    )
    mid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute("INSERT INTO uids (message_num, uid) VALUES (?, ?)", (mid, "msgid888"))
    conn.execute("INSERT INTO labels (message_num, label) VALUES (?, ?)", (mid, "SPAM"))
    conn.commit()
    conn.close()
    mdir = tmp_path / "Maildir"
    import_mbox_tree_to_maildir(mbox_root=root, maildir_root=mdir)
    spam_msgs = list_messages(mdir, folder_id=".SPAM", limit=10, offset=0)
    assert len(spam_msgs) == 1
    assert spam_msgs[0].subject == "Uid map"


def test_backslash_message_filename_normalized(tmp_path: Path) -> None:
    root = tmp_path / "gyb_export"
    eml = root / "2024" / "1" / "15" / "msgid999.eml"
    eml.parent.mkdir(parents=True)
    eml.write_bytes(b"Subject: Backslash key\nFrom: a@b.com\n\nb\n")
    conn = sqlite3.connect(root / "msg-db.sqlite")
    conn.executescript(_GYB_DB_SCHEMA)
    conn.execute(
        "INSERT INTO messages (message_filename, message_internaldate) VALUES (?, ?)",
        ("2024\\1\\15\\msgid999.eml", "2024-01-15 00:00:00"),
    )
    mid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute("INSERT INTO labels (message_num, label) VALUES (?, ?)", (mid, "DRAFT"))
    conn.commit()
    conn.close()
    mdir = tmp_path / "Maildir"
    import_mbox_tree_to_maildir(mbox_root=root, maildir_root=mdir)
    d_msgs = list_messages(mdir, folder_id=".DRAFT", limit=5, offset=0)
    assert len(d_msgs) == 1
    assert d_msgs[0].subject == "Backslash key"


def test_rebuild_maildir_from_local_gyb_workdir(tmp_path: Path) -> None:
    from app.services.maildir_service import rebuild_maildir_from_local_gyb_workdir

    gyb, _ = _write_gyb_with_sqlite(tmp_path)
    mdir = tmp_path / "rebuilt_maildir"
    stats = rebuild_maildir_from_local_gyb_workdir(work_root=gyb, maildir_root=mdir)
    assert stats.messages == 1
    folders = {fid for fid, _ in list_maildir_folders(mdir)}
    assert ".SENT" in folders


def test_rebuild_requires_msg_db(tmp_path: Path) -> None:
    import pytest

    from app.services.maildir_service import rebuild_maildir_from_local_gyb_workdir

    gyb = tmp_path / "gyb"
    (gyb / "2024" / "1" / "1").mkdir(parents=True)
    (gyb / "2024" / "1" / "1" / "x.eml").write_bytes(b"Subject: x\n\ny\n")
    mdir = tmp_path / "m"
    with pytest.raises(ValueError, match="gyb_msg_db_missing"):
        rebuild_maildir_from_local_gyb_workdir(work_root=gyb, maildir_root=mdir)
