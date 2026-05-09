"""Tests del plan de subida ZIP al vault Gmail."""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.services.gmail_vault_plan_service import resolve_gmail_zip_upload_plan


def test_bootstrap_immediate_uploads_without_prior_seal() -> None:
    d = resolve_gmail_zip_upload_plan(
        {"bootstrap_upload_immediate": True, "vault_anchor_dow": 6},
        last_sealed_at=None,
        now_utc=datetime(2026, 5, 8, 15, 0, tzinfo=timezone.utc),
        task_timezone="America/Bogota",
    )
    assert d.should_upload is True
    assert d.seal_kind == "bootstrap"


def test_bootstrap_waits_anchor_when_no_immediate() -> None:
    # 2026-05-08 = viernes en UTC; Bogotá también viernes (UTC-5)
    d = resolve_gmail_zip_upload_plan(
        {"bootstrap_upload_immediate": False, "vault_anchor_dow": 6},
        last_sealed_at=None,
        now_utc=datetime(2026, 5, 8, 15, 0, tzinfo=timezone.utc),
        task_timezone="America/Bogota",
    )
    assert d.should_upload is False
    assert "anchor" in d.reason or "bootstrap_waiting" in d.reason


def test_weekly_anchor_sunday_uploads() -> None:
    sealed = datetime(2026, 5, 1, 12, 0, tzinfo=ZoneInfo("America/Bogota"))
    # Domingo 2026-05-10
    d = resolve_gmail_zip_upload_plan(
        {"vault_zip_cadence": "weekly", "vault_anchor_dow": 6, "bootstrap_upload_immediate": True},
        last_sealed_at=sealed,
        now_utc=datetime(2026, 5, 10, 15, 0, tzinfo=timezone.utc),
        task_timezone="America/Bogota",
    )
    assert d.should_upload is True
    assert d.seal_kind == "weekly"
    assert d.period_start.isoformat() == "2026-05-02"


def test_weekly_wrong_dow_skips() -> None:
    sealed = datetime(2026, 5, 1, 12, 0, tzinfo=ZoneInfo("America/Bogota"))
    d = resolve_gmail_zip_upload_plan(
        {"vault_zip_cadence": "weekly", "vault_anchor_dow": 6},
        last_sealed_at=sealed,
        now_utc=datetime(2026, 5, 8, 15, 0, tzinfo=timezone.utc),
        task_timezone="America/Bogota",
    )
    assert d.should_upload is False


def test_cadence_none_skips_after_first_seal() -> None:
    sealed = datetime(2026, 5, 1, 12, 0, tzinfo=ZoneInfo("America/Bogota"))
    d = resolve_gmail_zip_upload_plan(
        {"vault_zip_cadence": "none", "vault_anchor_dow": 6},
        last_sealed_at=sealed,
        now_utc=datetime(2026, 5, 10, 15, 0, tzinfo=timezone.utc),
        task_timezone="America/Bogota",
    )
    assert d.should_upload is False
    assert "cadence_none" in d.reason


def test_same_day_no_double_seal() -> None:
    sealed = datetime(2026, 5, 10, 8, 0, tzinfo=ZoneInfo("America/Bogota"))
    d = resolve_gmail_zip_upload_plan(
        {"vault_zip_cadence": "weekly", "vault_anchor_dow": 6},
        last_sealed_at=sealed,
        now_utc=datetime(2026, 5, 10, 20, 0, tzinfo=timezone.utc),
        task_timezone="America/Bogota",
    )
    assert d.should_upload is False
    assert "already_sealed" in d.reason
