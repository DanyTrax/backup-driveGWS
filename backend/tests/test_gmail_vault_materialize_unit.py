"""Tests unitarios materialización vault ZIP (sin rclone ni BD)."""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.services.gmail_vault_zip_layout import gmail_vault_zip_object_rel_from_lsjson

from app.services.gmail_vault_materialize_logic import (
    GmailVaultMaterializeError,
    VaultZipIndexEntry,
    merge_materialized_session_into_gyb_workdir,
    parse_lsjson_zip_entries,
    period_overlaps_window,
    resolve_materialize_window,
    select_zip_entries_for_window,
)


def test_resolve_single_day() -> None:
    d = date(2026, 5, 10)
    a, b = resolve_materialize_window("single_day", anchor_date=d, date_from=None, date_to=None, calendar_month=None)
    assert a == b == d


def test_resolve_month() -> None:
    a, b = resolve_materialize_window(
        "month",
        anchor_date=None,
        date_from=None,
        date_to=None,
        calendar_month="2026-02",
    )
    assert a == date(2026, 2, 1)
    assert b == date(2026, 2, 28)


def test_resolve_month_invalid() -> None:
    with pytest.raises(GmailVaultMaterializeError):
        resolve_materialize_window(
            "month",
            anchor_date=None,
            date_from=None,
            date_to=None,
            calendar_month="2026-13",
        )


def test_period_overlap() -> None:
    assert period_overlaps_window(date(2026, 5, 1), date(2026, 5, 7), date(2026, 5, 5), date(2026, 5, 10)) is True
    assert period_overlaps_window(date(2026, 5, 1), date(2026, 5, 4), date(2026, 5, 5), date(2026, 5, 10)) is False


def test_select_zip_entries() -> None:
    entries = [
        VaultZipIndexEntry("BOOTSTRAP/2026-05-01__2026-05-07.zip", date(2026, 5, 1), date(2026, 5, 7), 1),
        VaultZipIndexEntry("WEEKLY/2026-06-01__2026-06-30.zip", date(2026, 6, 1), date(2026, 6, 30), 1),
    ]
    picked = select_zip_entries_for_window(entries, date(2026, 5, 5), date(2026, 5, 10))
    assert len(picked) == 1
    assert "BOOTSTRAP" in picked[0].rel_path


def test_gmail_vault_zip_object_rel_from_lsjson() -> None:
    aid = uuid.UUID("06c080f5-e017-42ee-a450-5bddb88e11f4")
    rel = gmail_vault_zip_object_rel_from_lsjson(aid, "BOOTSTRAP/2026-05-10__2026-05-10.zip")
    assert rel.startswith("1-GMAIL/zips/")
    assert str(aid) in rel
    assert rel.endswith("BOOTSTRAP/2026-05-10__2026-05-10.zip")


def test_parse_lsjson_zips() -> None:
    stdout = """[
      {"Path":"BOOTSTRAP/2026-05-01__2026-05-07.zip","Name":"2026-05-01__2026-05-07.zip","Size":100,"IsDir":false},
      {"Path":"skip.txt","Name":"skip.txt","Size":1,"IsDir":false},
      {"Path":"bad.zip","Name":"bad.zip","Size":1,"IsDir":false}
    ]"""
    rows = parse_lsjson_zip_entries(stdout)
    assert len(rows) == 1
    assert rows[0].period_start == date(2026, 5, 1)


def test_merge_materialized_session_into_gyb_workdir(tmp_path) -> None:
    root = tmp_path / "session"
    ext = root / "extracted" / "period_a"
    gyb = tmp_path / "gyb"
    (ext / "subdir").mkdir(parents=True)
    (ext / "subdir" / "hello.txt").write_text("x", encoding="utf-8")
    staging = root / "staging"
    staging.mkdir()
    z = staging / "dummy.zip"
    z.write_bytes(b"PK")

    n = merge_materialized_session_into_gyb_workdir(root, gyb)
    assert n == 1
    assert (gyb / "subdir" / "hello.txt").read_text(encoding="utf-8") == "x"
    assert not (root / "extracted").exists()
    assert not z.exists()


def test_merge_materialized_session_no_extracted_raises(tmp_path) -> None:
    root = tmp_path / "session"
    root.mkdir()
    gyb = tmp_path / "gyb"
    with pytest.raises(GmailVaultMaterializeError, match="materialize_no_extracted"):
        merge_materialized_session_into_gyb_workdir(root, gyb)
