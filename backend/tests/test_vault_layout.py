"""Tests for vault path layout (1-GMAIL / 2-DRIVE)."""
from __future__ import annotations

from datetime import datetime, timezone

from app.services import vault_layout


def test_separated_default() -> None:
    assert vault_layout.use_separated_vault_layout({}) is True
    assert vault_layout.use_separated_vault_layout(None) is True


def test_legacy_disables_separated() -> None:
    assert vault_layout.use_separated_vault_layout({"vault_legacy_layout": True}) is False


def test_gmail_rclone_subpath() -> None:
    assert vault_layout.gmail_vault_rclone_subpath() == "1-GMAIL/gyb_mbox"


def test_drive_dest_continuous() -> None:
    d = datetime(2025, 4, 23, 10, 0, tzinfo=timezone.utc)
    s = vault_layout.drive_dest_subpath_for_task({}, now=d)
    assert s == "2-DRIVE/_sync"


def test_drive_dest_dated_with_kind_total() -> None:
    d = datetime(2025, 4, 23, 10, 0, tzinfo=timezone.utc)
    s = vault_layout.drive_dest_subpath_for_task(
        {
            "drive_layout": "dated_run",
            "drive_run_kind": "TOTAL",
        },
        now=d,
    )
    assert s == "2-DRIVE/MSA_Runs/2025-04-23T10-00 (TOTAL)"


def test_drive_dest_dated_no_kind() -> None:
    d = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
    s = vault_layout.drive_dest_subpath_for_task(
        {"drive_layout": "dated_run"},
        now=d,
    )
    assert s == "2-DRIVE/MSA_Runs/2025-01-02T03-04"


def test_drive_dest_legacy_dated() -> None:
    d = datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc)
    s = vault_layout.drive_dest_subpath_for_task(
        {"drive_layout": "dated_run", "vault_legacy_layout": True},
        now=d,
    )
    assert s == "MSA_Runs/2025-06-01T12-00"


def test_purge_gyb_workdir_flag() -> None:
    assert vault_layout.gmail_purge_gyb_workdir_after_vault_verified({}) is False
    assert vault_layout.gmail_purge_gyb_workdir_after_vault_verified(
        {"gmail_purge_gyb_workdir_after_vault_verified": True}
    ) is True
    assert (
        vault_layout.gmail_purge_gyb_workdir_after_vault_verified(
            {
                "gmail_purge_gyb_workdir_after_vault_verified": True,
                "vault_gmail_disable_push": True,
            }
        )
        is False
    )
