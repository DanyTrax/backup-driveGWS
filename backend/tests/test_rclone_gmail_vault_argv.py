"""rclone argv para copia local → vault (GYB Maildir)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services.rclone_service import (
    RcloneConfig,
    build_rclone_check_local_vault_argv,
    build_rclone_local_to_vault_argv,
)


def _vault_mock(**kwargs: object) -> MagicMock:
    base = dict(
        rclone_gmail_vault_transfers=24,
        rclone_gmail_vault_checkers=12,
        rclone_gmail_vault_tpslimit=0,
        rclone_gmail_vault_tpslimit_burst=0,
        rclone_gmail_vault_compare="size_only",
        rclone_gmail_vault_no_traverse=False,
        rclone_gmail_vault_extra_flags="",
    )
    base.update(kwargs)
    return MagicMock(**base)


def test_local_to_vault_argv_uses_parallelism_and_fast_list() -> None:
    cfg = RcloneConfig(
        config_path="/tmp/rclone.test.conf",
        remote_source="",
        remote_dest="dest:",
        cleanup_paths=[],
    )
    with patch("app.services.rclone_service.get_settings", return_value=_vault_mock()):
        argv = build_rclone_local_to_vault_argv(
            "/data/maildir",
            cfg,
            dest_subpath="1-GMAIL/gyb_mbox",
        )
    assert argv[:2] == ["copy", str(Path("/data/maildir").resolve())]
    assert argv[argv.index("--transfers") + 1] == "24"
    assert argv[argv.index("--checkers") + 1] == "12"
    assert "--fast-list" in argv
    assert "--size-only" in argv
    assert "dest:1-GMAIL/gyb_mbox/" in argv
    assert "--no-traverse" not in argv


def test_local_to_vault_argv_no_traverse_when_enabled() -> None:
    cfg = RcloneConfig(
        config_path="/tmp/rclone.test.conf",
        remote_source="",
        remote_dest="dest:",
        cleanup_paths=[],
    )
    with patch(
        "app.services.rclone_service.get_settings",
        return_value=_vault_mock(rclone_gmail_vault_no_traverse=True),
    ):
        argv = build_rclone_local_to_vault_argv(
            "/data/maildir",
            cfg,
            dest_subpath="1-GMAIL/gyb_mbox",
        )
    assert "--no-traverse" in argv


def test_local_to_vault_argv_tps_and_compare_and_extra() -> None:
    cfg = RcloneConfig(
        config_path="/tmp/rclone.test.conf",
        remote_source="",
        remote_dest="dest:",
        cleanup_paths=[],
    )
    with patch(
        "app.services.rclone_service.get_settings",
        return_value=_vault_mock(
            rclone_gmail_vault_compare="default",
            rclone_gmail_vault_tpslimit=12,
            rclone_gmail_vault_tpslimit_burst=24,
            rclone_gmail_vault_extra_flags="--drive-pacer-min-sleep 100ms",
        ),
    ):
        argv = build_rclone_local_to_vault_argv(
            "/data/m",
            cfg,
            dest_subpath="1-GMAIL/gyb_mbox",
        )
    assert "--size-only" not in argv
    assert argv[argv.index("--tpslimit") + 1] == "12"
    assert argv[argv.index("--tpslimit-burst") + 1] == "24"
    assert argv[-2:] == ["--drive-pacer-min-sleep", "100ms"]


def test_check_vault_argv_includes_fast_list_and_settings_flags() -> None:
    cfg = RcloneConfig(
        config_path="/tmp/rclone.test.conf",
        remote_source="",
        remote_dest="dest:",
        cleanup_paths=[],
    )
    with patch(
        "app.services.rclone_service.get_settings",
        return_value=_vault_mock(
            rclone_gmail_vault_compare="checksum",
            rclone_gmail_vault_tpslimit=8,
        ),
    ):
        argv = build_rclone_check_local_vault_argv(
            "/data/m",
            cfg,
            dest_subpath="1-GMAIL/gyb_mbox",
        )
    assert argv[0] == "check"
    assert "--one-way" in argv
    assert "--fast-list" in argv
    assert "--checksum" in argv
    assert argv[argv.index("--tpslimit") + 1] == "8"
    assert argv[argv.index("--checkers") + 1] == "12"
    assert "--tpslimit-burst" not in argv
