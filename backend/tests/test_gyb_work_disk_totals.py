"""Totales de disco para inventario GYB / mail purge."""
from __future__ import annotations

from pathlib import Path

from app.services.mail_purge_service import compute_gyb_work_disk_totals, scan_gyb_work_for_list_row


def test_compute_gyb_work_disk_totals_counts_eml_and_total(tmp_path: Path) -> None:
    root = tmp_path / "gyb"
    (root / "a").mkdir(parents=True)
    (root / "a" / "m.eml").write_bytes(b"hello eml")
    (root / "msg-db.sqlite").write_bytes(b"db")
    (root / "readme.txt").write_text("x", encoding="utf-8")
    total, export_b, n = compute_gyb_work_disk_totals(root)
    assert total == 12  # .eml (9 B) + sqlite (2) + .txt (1)
    assert export_b == 9
    assert n == 1


def test_scan_gyb_work_for_list_row_single_walk(tmp_path: Path) -> None:
    root = tmp_path / "gyb"
    (root / "a").mkdir(parents=True)
    (root / "a" / "m.eml").write_bytes(b"x")
    has_ex, total = scan_gyb_work_for_list_row(root)
    assert has_ex is True
    assert total == 1


def test_compute_gyb_work_disk_totals_missing_dir(tmp_path: Path) -> None:
    total, export_b, n = compute_gyb_work_disk_totals(tmp_path / "nope")
    assert total is None and export_b is None and n == 0
