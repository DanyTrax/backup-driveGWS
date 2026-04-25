"""Sondeo de progreso Gmail (conteo en disco)."""
from __future__ import annotations

from pathlib import Path

from app.utils.gmail_export_counts import count_gyb_export, count_maildir_messages


def test_count_gyb_export_empty(tmp_path: Path) -> None:
    w = tmp_path / "export"
    w.mkdir()
    assert count_gyb_export(w) == (0, 0, 0)


def test_count_gyb_export_eml(tmp_path: Path) -> None:
    w = tmp_path / "e"
    w.mkdir()
    (w / "a.eml").write_text("m1", encoding="utf-8")
    (w / "b.eml").write_text("m2m2", encoding="utf-8")
    m, b, f = count_gyb_export(w)
    assert m == 2
    assert f == 2
    assert b == 6  # "m1" (2) + "m2m2" (4)


def test_count_maildir_cur_new(tmp_path: Path) -> None:
    m = tmp_path / "m"
    (m / "cur").mkdir(parents=True)
    (m / "new").mkdir(parents=True)
    (m / "cur" / "1").write_text("a", encoding="utf-8")
    (m / "new" / "2").write_text("bb", encoding="utf-8")
    n, b, f = count_maildir_messages(m)
    assert n == 2
    assert f == 2
    assert b == 3
