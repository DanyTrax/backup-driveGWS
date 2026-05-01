"""Tests for vault path layout (1-GMAIL / 2-DRIVE)."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from app.services import vault_layout


def test_separated_default() -> None:
    assert vault_layout.use_separated_vault_layout({}) is True
    assert vault_layout.use_separated_vault_layout(None) is True


def test_legacy_disables_separated() -> None:
    assert vault_layout.use_separated_vault_layout({"vault_legacy_layout": True}) is False


def test_gmail_rclone_subpath() -> None:
    assert vault_layout.gmail_vault_rclone_subpath() == "1-GMAIL/gyb_mbox"


def test_vault_dir_reports_constants() -> None:
    assert vault_layout.VAULT_DIR_REPORTS == "3-REPORTS"
    assert vault_layout.VAULT_REPORTS_SUBDIR_REPORTS == "reports"
    assert vault_layout.VAULT_REPORTS_SUBDIR_LOGS == "logs"


def test_dated_chain_run_incremental_folder_name() -> None:
    d = datetime(2025, 4, 23, 10, 0, tzinfo=timezone.utc)
    s = vault_layout.drive_dest_subpath_for_task(
        {"drive_layout": "dated_run"},
        now=d,
        dated_chain_run="incremental",
    )
    assert s == "2-DRIVE/MSA_Runs/2025-04-23T10-00 (INC)"


def test_dated_snapshot_dest_subpath_compare() -> None:
    p = vault_layout.dated_run_snapshot_dest_subpath(
        {"drive_layout": "dated_run"},
        "2025-04-22T09-00 (TOTAL)",
    )
    assert p == "2-DRIVE/MSA_Runs/2025-04-22T09-00 (TOTAL)"


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


def test_drive_dest_dated_uses_wall_clock_tz_when_now_omitted() -> None:
    """El sello MSA_Runs sigue la zona indicada (operación en Bogota)."""
    with patch("app.services.vault_layout.datetime") as mock_dt:
        mock_dt.now.side_effect = lambda tz: datetime(2025, 7, 20, 19, 45, tzinfo=tz)
        s = vault_layout.drive_dest_subpath_for_task(
            {"drive_layout": "dated_run"},
            now=None,
            tz_name="America/Bogota",
        )
    assert s == "2-DRIVE/MSA_Runs/2025-07-20T19-45"


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


def test_gmail_skip_maildir_import_flag() -> None:
    assert vault_layout.gmail_skip_maildir_import({}) is False
    assert vault_layout.gmail_skip_maildir_import(None) is False
    assert vault_layout.gmail_skip_maildir_import({"gmail_skip_maildir_import": True}) is True
    assert vault_layout.gmail_skip_maildir_import({"gmail_skip_maildir_import": False}) is False


def test_vault_reports_logs_base_subpath() -> None:
    assert vault_layout.vault_reports_logs_base_subpath() == "3-REPORTS/logs"


def test_vault_success_reports_enabled_default() -> None:
    assert vault_layout.vault_success_reports_enabled({}) is True
    assert vault_layout.vault_success_reports_enabled(None) is True
    assert vault_layout.vault_success_reports_enabled({"vault_disable_success_reports": True}) is False


def test_drive_dest_computadoras_continuous() -> None:
    d = datetime(2025, 4, 23, 10, 0, tzinfo=timezone.utc)
    s = vault_layout.drive_dest_subpath_for_task({}, now=d, backup_scope="drive_computadoras")
    assert s == "2-DRIVE/_computadoras"


def test_drive_dest_computadoras_dated_total() -> None:
    d = datetime(2025, 4, 23, 10, 0, tzinfo=timezone.utc)
    s = vault_layout.drive_dest_subpath_for_task(
        {
            "drive_layout": "dated_run",
            "drive_run_kind": "TOTAL",
        },
        now=d,
        backup_scope="drive_computadoras",
    )
    assert s == "2-DRIVE/MSA_Runs/2025-04-23T10-00 (TOTAL)/computadoras"


def test_drive_dest_legacy_dated_computadoras() -> None:
    d = datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc)
    s = vault_layout.drive_dest_subpath_for_task(
        {"drive_layout": "dated_run", "vault_legacy_layout": True},
        now=d,
        backup_scope="drive_computadoras",
    )
    assert s == "MSA_Runs/2025-06-01T12-00/computadoras"
