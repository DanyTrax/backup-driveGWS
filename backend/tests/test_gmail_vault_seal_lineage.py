"""Tests herencia de sellado ZIP (línea histórica vault / cuenta)."""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from app.services.gmail_vault_materialize_logic import VaultZipIndexEntry
from app.services.gmail_vault_seal_lineage import (
    SealLineage,
    latest_zip_seal_from_entries,
    pick_best_lineage,
    sealed_at_end_of_day,
)


def test_latest_zip_seal_picks_max_period_end() -> None:
    aid = uuid.uuid4()
    entries = [
        VaultZipIndexEntry("WEEKLY/2026-07-01__2026-07-07.zip", date(2026, 7, 1), date(2026, 7, 7), 10),
        VaultZipIndexEntry(
            "MANUAL/2026-08-10__2026-08-10.zip", date(2026, 8, 10), date(2026, 8, 10), 20
        ),
        VaultZipIndexEntry("BOOTSTRAP/2026-01-01__2026-01-01.zip", date(2026, 1, 1), date(2026, 1, 1), 5),
    ]
    lineage = latest_zip_seal_from_entries(entries, account_id=aid)
    assert lineage is not None
    assert lineage.source == "vault_zip"
    assert lineage.period_end == date(2026, 8, 10)
    assert lineage.zip_rel_path is not None
    assert "2026-08-10__2026-08-10.zip" in lineage.zip_rel_path


def test_pick_best_lineage_prefers_newer() -> None:
    older = SealLineage(
        last_sealed_at=datetime(2026, 5, 1, tzinfo=UTC),
        source="task_db",
    )
    newer = SealLineage(
        last_sealed_at=datetime(2026, 8, 10, tzinfo=UTC),
        source="vault_zip",
        period_end=date(2026, 8, 10),
    )
    best = pick_best_lineage(older, None, newer)
    assert best is not None
    assert best.source == "vault_zip"


def test_sealed_at_end_of_day_bogota() -> None:
    dt = sealed_at_end_of_day(date(2026, 8, 10), task_timezone="America/Bogota")
    assert dt.tzinfo is not None
    # 23:59:59 Bogotá = next day 04:59:59 UTC (sin DST en Bogotá)
    assert dt.astimezone(UTC).day in (10, 11)
