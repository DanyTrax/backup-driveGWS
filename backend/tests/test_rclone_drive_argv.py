"""Argv rclone copy/sync Drive → vault (sin token suelto ``false``)."""
from __future__ import annotations

from app.services.rclone_service import RcloneConfig, build_rclone_argv


def test_build_rclone_argv_server_side_flag_is_one_token() -> None:
    cfg = RcloneConfig(
        config_path="/tmp/rclone.conf",
        remote_source="source:",
        remote_dest="dest:",
        cleanup_paths=[],
    )
    argv = build_rclone_argv(
        cfg,
        mode="copy",
        subpath="Computadoras/",
        dest_subpath="2-DRIVE/MSA_Runs/2026-04-29T06-25",
        dry_run=False,
    )
    assert argv[0] == "copy"
    assert argv[1] == "source:Computadoras/"
    assert argv[2] == "dest:2-DRIVE/MSA_Runs/2026-04-29T06-25"
    assert "--drive-server-side-across-configs=false" in argv
    assert argv.count("false") == 0
