"""Tests reseed GYB tras purga (filtro after: desde sellado ZIP)."""
from __future__ import annotations

from datetime import UTC, datetime, timezone
from pathlib import Path

from app.services.gmail_vault_gyb_reseed import (
    gmail_search_after_sealed,
    gyb_workdir_needs_date_reseed,
    resolve_gyb_search_after_workdir_purge,
    sealed_fetch_start_date,
)


def test_sealed_fetch_start_with_overlap() -> None:
    sealed = datetime(2026, 5, 10, 15, 0, tzinfo=UTC)
    start = sealed_fetch_start_date(sealed, overlap_days=1, task_timezone="America/Bogota")
    # 15:00 UTC = 10:00 Bogotá → 2026-05-10 local; −1 día → 2026-05-09
    assert start.isoformat() == "2026-05-09"


def test_gmail_search_after_is_inclusive_via_exclusive_day() -> None:
    sealed = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)
    q = gmail_search_after_sealed(sealed, overlap_days=1, task_timezone="UTC")
    # start inclusivo 2026-05-09 → after:2026/05/08
    assert q == "after:2026/05/08"


def test_reseed_none_when_workdir_has_eml(tmp_path: Path) -> None:
    (tmp_path / "a.eml").write_text("x", encoding="utf-8")
    sealed = datetime(2026, 5, 10, tzinfo=UTC)
    assert gyb_workdir_needs_date_reseed(tmp_path) is False
    assert (
        resolve_gyb_search_after_workdir_purge(
            work_root=tmp_path,
            last_sealed_at=sealed,
            filters={"overlap_days": 1},
            task_timezone="UTC",
        )
        is None
    )


def test_reseed_search_when_empty_and_sealed(tmp_path: Path) -> None:
    sealed = datetime(2026, 5, 10, 12, 0, tzinfo=UTC)
    q = resolve_gyb_search_after_workdir_purge(
        work_root=tmp_path,
        last_sealed_at=sealed,
        filters={"overlap_days": 1},
        task_timezone="UTC",
    )
    assert q == "after:2026/05/08"


def test_reseed_none_without_seal(tmp_path: Path) -> None:
    assert (
        resolve_gyb_search_after_workdir_purge(
            work_root=tmp_path,
            last_sealed_at=None,
            filters={},
            task_timezone="UTC",
        )
        is None
    )
