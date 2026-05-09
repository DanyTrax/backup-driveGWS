"""Tests unitarios materialización vault ZIP (sin rclone ni BD)."""
from __future__ import annotations

from datetime import date

import pytest

from app.services.gmail_vault_materialize_logic import (
    GmailVaultMaterializeError,
    VaultZipIndexEntry,
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


def test_parse_lsjson_zips() -> None:
    stdout = """[
      {"Path":"BOOTSTRAP/2026-05-01__2026-05-07.zip","Name":"2026-05-01__2026-05-07.zip","Size":100,"IsDir":false},
      {"Path":"skip.txt","Name":"skip.txt","Size":1,"IsDir":false},
      {"Path":"bad.zip","Name":"bad.zip","Size":1,"IsDir":false}
    ]"""
    rows = parse_lsjson_zip_entries(stdout)
    assert len(rows) == 1
    assert rows[0].period_start == date(2026, 5, 1)
