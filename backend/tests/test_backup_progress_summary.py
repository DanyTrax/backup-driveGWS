"""Tests resumen de progreso al cerrar logs."""
from __future__ import annotations

from app.services.backup_progress_summary import format_completion_summary_from_event


def test_vault_zip_done_summary() -> None:
    s = format_completion_summary_from_event(
        {"stage": "vault_zip_done", "vault_rel_zip": "1-GMAIL/zips/uuid/WEEKLY/foo.zip"}
    )
    assert s is not None
    assert "Sellado ZIP" in s
    assert "foo.zip" in s


def test_vault_zip_skipped_summary() -> None:
    s = format_completion_summary_from_event(
        {"stage": "vault_zip_skipped", "reason": "already_sealed_today"}
    )
    assert s is not None
    assert "omitida" in s


def test_vault_push_ok_summary() -> None:
    s = format_completion_summary_from_event(
        {"stage": "vault_push", "ok": True, "subpath": "1-GMAIL/gyb_mbox"}
    )
    assert s is not None
    assert "gyb_mbox" in s
