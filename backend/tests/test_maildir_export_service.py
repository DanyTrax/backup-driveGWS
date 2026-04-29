"""Tests for Maildir ZIP export helper."""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from app.services.maildir_export_service import (
    MaildirExportTooLarge,
    build_maildir_zip_file,
    safe_maildir_zip_stem,
)


def test_safe_maildir_zip_stem() -> None:
    assert safe_maildir_zip_stem("User@Example.com") == "user_at_example.com"
    assert safe_maildir_zip_stem("") == "mailbox"


def test_build_maildir_zip_roundtrip(tmp_path: Path) -> None:
    root = tmp_path / "Maildir"
    (root / "cur").mkdir(parents=True)
    (root / "new").mkdir(parents=True)
    (root / "tmp").mkdir(parents=True)
    f = root / "cur" / "msg1"
    f.write_text("From: a\n\nbody", encoding="utf-8")

    zpath = build_maildir_zip_file(root, max_total_bytes=0)
    try:
        assert zpath.is_file()
        with zipfile.ZipFile(zpath) as zf:
            names = sorted(zf.namelist())
        assert "cur/msg1" in names
    finally:
        zpath.unlink(missing_ok=True)


def test_build_maildir_zip_respects_max_bytes(tmp_path: Path) -> None:
    root = tmp_path / "Maildir"
    (root / "cur").mkdir(parents=True)
    (root / "cur" / "a").write_bytes(b"x" * 100)
    (root / "cur" / "b").write_bytes(b"y" * 100)

    with pytest.raises(MaildirExportTooLarge):
        build_maildir_zip_file(root, max_total_bytes=150)
