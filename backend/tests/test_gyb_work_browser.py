"""Visor de export GYB local: etiquetas ES, orden, alcance global, búsqueda ampliada."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.services.gyb_work_browser_service import (
    gyb_gmail_label_display_name,
    list_gyb_eml_summaries,
    list_gyb_eml_summaries_for_label,
)


def test_label_display_spanish_system_names() -> None:
    assert gyb_gmail_label_display_name("INBOX") == "Bandeja de entrada"
    assert gyb_gmail_label_display_name("SENT") == "Enviados"
    assert gyb_gmail_label_display_name("CATEGORY_FORUMS") == "Foros"
    assert gyb_gmail_label_display_name("Mi etiqueta") == "Mi etiqueta"


def test_sort_by_header_date_desc(tmp_path: Path) -> None:
    root = tmp_path / "gyb"
    root.mkdir()
    tz = timezone.utc
    t_old = datetime(2020, 1, 1, 12, 0, tzinfo=tz)
    t_new = datetime(2024, 6, 15, 8, 0, tzinfo=tz)
    old = root / "a.eml"
    new = root / "b.eml"
    old.write_text(
        f"Subject: Old\nFrom: x@y.z\nDate: {t_old.strftime('%a, %d %b %Y %H:%M:%S +0000')}\n\n.\n",
        encoding="utf-8",
    )
    new.write_text(
        f"Subject: New\nFrom: x@y.z\nDate: {t_new.strftime('%a, %d %b %Y %H:%M:%S +0000')}\n\n.\n",
        encoding="utf-8",
    )
    t_touch = datetime(2010, 1, 1, tzinfo=tz).timestamp()
    old.touch()
    new_mtime = (t_new + timedelta(days=1)).timestamp()
    new.touch()
    import os

    os.utime(old, (t_touch, t_touch))
    os.utime(new, (new_mtime, new_mtime))

    page = list_gyb_eml_summaries(
        root,
        folder_id="",
        limit=10,
        offset=0,
        sort_by="header_date",
        sort_order="desc",
    )
    assert [x.subject for x in page.items] == ["New", "Old"]
    assert page.total_in_scope == 2
    assert page.total_matches == 2
    assert page.has_more is False

    page_asc = list_gyb_eml_summaries(
        root,
        folder_id="",
        limit=10,
        offset=0,
        sort_by="header_date",
        sort_order="asc",
    )
    assert [x.subject for x in page_asc.items] == ["Old", "New"]


def test_search_matches_to_cc(tmp_path: Path) -> None:
    root = tmp_path / "gyb"
    root.mkdir()
    eml = root / "x.eml"
    eml.write_text(
        "Subject: X\nFrom: a@a.com\nTo: cliente_unico@empresa.test\nCc: otro@b.com\n\n",
        encoding="utf-8",
    )
    page = list_gyb_eml_summaries(
        root,
        folder_id="",
        q="cliente_unico",
        limit=10,
        offset=0,
    )
    assert len(page.items) == 1
    assert page.total_matches == 1


def test_list_scope_all_labels_and_tag_list(tmp_path: Path) -> None:
    root = tmp_path / "gyb"
    root.mkdir()
    eml = root / "m.eml"
    eml.write_bytes(b"Subject: One\nFrom: a@b\n\nx\n")
    db = root / "msg-db.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE messages (message_num INTEGER PRIMARY KEY, message_filename TEXT);
        CREATE TABLE labels (message_num INTEGER, label TEXT);
        """
    )
    conn.execute(
        "INSERT INTO messages (message_filename) VALUES (?)",
        (str(eml.relative_to(root)).replace("\\", "/"),),
    )
    mid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute("INSERT INTO labels (message_num, label) VALUES (?, ?)", (mid, "INBOX"))
    conn.execute("INSERT INTO labels (message_num, label) VALUES (?, ?)", (mid, "SENT"))
    conn.commit()
    conn.close()

    page = list_gyb_eml_summaries_for_label(
        root,
        label="",
        limit=10,
        offset=0,
        list_scope="all",
    )
    assert len(page.items) == 1
    assert page.items[0].subject == "One"
    assert page.items[0].labels is not None
    assert "INBOX" in page.items[0].labels
    assert "SENT" in page.items[0].labels
