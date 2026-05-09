"""Validación filters_json vault ZIP en tareas (Fase 4)."""
from __future__ import annotations

import pytest

from app.schemas.task_filters_gmail_vault import normalize_task_filters_for_scope


def test_normalize_zip_only_clamps_and_defaults() -> None:
    f = normalize_task_filters_for_scope(
        {
            "gmail_vault_packaging": "zip_only",
            "vault_zip_cadence": "monthly",
            "vault_anchor_dow": "3",
            "overlap_days": 999,
        },
        scope="gmail",
    )
    assert f["gmail_vault_packaging"] == "zip_only"
    assert f["vault_zip_cadence"] == "monthly"
    assert f["vault_anchor_dow"] == 3
    assert f["overlap_days"] == 366
    assert f["bootstrap_upload_immediate"] is True


def test_normalize_rejects_drive_scope_with_zip_filters() -> None:
    with pytest.raises(ValueError, match="gmail_scope"):
        normalize_task_filters_for_scope(
            {"gmail_vault_packaging": "zip_only"},
            scope="drive_root",
        )


def test_normalize_rejects_zip_options_without_zip_packaging() -> None:
    with pytest.raises(ValueError, match="zip_only_or_mixed"):
        normalize_task_filters_for_scope(
            {"vault_zip_cadence": "weekly"},
            scope="gmail",
        )


def test_normalize_rejects_cadence_with_legacy_packaging() -> None:
    with pytest.raises(ValueError, match="zip_only_or_mixed"):
        normalize_task_filters_for_scope(
            {
                "gmail_vault_packaging": "legacy_eml",
                "vault_zip_cadence": "weekly",
            },
            scope="gmail",
        )


def test_normalize_legacy_only_ok() -> None:
    f = normalize_task_filters_for_scope(
        {"gmail_vault_packaging": "legacy_eml"},
        scope="gmail",
    )
    assert f["gmail_vault_packaging"] == "legacy_eml"
    assert "vault_zip_cadence" not in f


def test_normalize_rejects_disable_push_with_zip() -> None:
    with pytest.raises(ValueError, match="incompatible"):
        normalize_task_filters_for_scope(
            {
                "gmail_vault_packaging": "mixed",
                "vault_zip_cadence": "weekly",
                "vault_gmail_disable_push": True,
            },
            scope="gmail",
        )


def test_normalize_full_scope_allows_zip_filters() -> None:
    f = normalize_task_filters_for_scope(
        {"gmail_vault_packaging": "zip_only", "vault_zip_cadence": "weekly"},
        scope="full",
    )
    assert f["gmail_vault_packaging"] == "zip_only"
