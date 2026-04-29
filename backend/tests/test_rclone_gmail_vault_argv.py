"""rclone argv para copia local → vault (GYB Maildir)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services.rclone_service import RcloneConfig, build_rclone_local_to_vault_argv


def test_local_to_vault_argv_uses_parallelism_and_fast_list() -> None:
    cfg = RcloneConfig(
        config_path="/tmp/rclone.test.conf",
        remote_source="",
        remote_dest="dest:",
        cleanup_paths=[],
    )
    mock_s = MagicMock(rclone_gmail_vault_transfers=24, rclone_gmail_vault_checkers=12)
    with patch("app.services.rclone_service.get_settings", return_value=mock_s):
        argv = build_rclone_local_to_vault_argv(
            "/data/maildir",
            cfg,
            dest_subpath="1-GMAIL/gyb_mbox",
        )
    assert argv[:2] == ["copy", str(Path("/data/maildir").resolve())]
    assert argv[argv.index("--transfers") + 1] == "24"
    assert argv[argv.index("--checkers") + 1] == "12"
    assert "--fast-list" in argv
    assert "dest:1-GMAIL/gyb_mbox/" in argv
