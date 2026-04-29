"""rclone argv para mkdir de destino Gmail vault."""
from __future__ import annotations

from app.services.rclone_service import RcloneConfig, build_rclone_mkdir_dest_argv


def test_mkdir_argv_gmail_subpath() -> None:
    cfg = RcloneConfig(
        config_path="/tmp/rclone.test.conf",
        remote_source="",
        remote_dest="dest:",
        cleanup_paths=[],
    )
    argv = build_rclone_mkdir_dest_argv(cfg, dest_subpath="  1-GMAIL/gyb_mbox/  ")
    assert argv[0] == "mkdir"
    assert argv[1] == "dest:1-GMAIL/gyb_mbox"
    assert "--config" in argv
    assert "/tmp/rclone.test.conf" in argv
