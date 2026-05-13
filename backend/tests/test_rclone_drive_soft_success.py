"""Parser de salida rclone Drive y política de rc para éxito con omisiones."""
from __future__ import annotations

from app.services.rclone_service import (
    RCLONE_RC_INSUFFICIENT_QUOTA,
    RCLONE_RC_INTERRUPTED,
    RCLONE_RC_SYNTAX,
    RCLONE_RC_SUCCESS,
    drive_rclone_should_fail_backup,
    summarize_rclone_drive_transfer_log,
)


def test_drive_rclone_should_fail_backup() -> None:
    assert drive_rclone_should_fail_backup(RCLONE_RC_SUCCESS) is False
    assert drive_rclone_should_fail_backup(3) is False
    assert drive_rclone_should_fail_backup(2) is False
    assert drive_rclone_should_fail_backup(RCLONE_RC_SYNTAX) is True
    assert drive_rclone_should_fail_backup(RCLONE_RC_INSUFFICIENT_QUOTA) is True
    assert drive_rclone_should_fail_backup(RCLONE_RC_INTERRUPTED) is True
    assert drive_rclone_should_fail_backup(6) is True


def test_summarize_extracts_paths_and_parents() -> None:
    out = """
2026/05/13 03:24:24 NOTICE: foo.pdf: Duplicate object found in source - ignoring
2026/05/13 05:31:02 ERROR : Documents/OTROS/DOCU NPC: Failed to update directory timestamp or metadata: directory not found
2026/05/13 05:31:03 ERROR : PLASTICS/sub: Failed to copy: dangling shortcut
"""
    text, n_err = summarize_rclone_drive_transfer_log(out, tail_chars=500)
    assert n_err == 2
    assert "Documents/OTROS" in text
    assert "PLASTICS" in text
    assert "Duplicate object" in text
    assert "Extracto final" in text


def test_summarize_rclone_drive_transfer_log_empty() -> None:
    t, n = summarize_rclone_drive_transfer_log("")
    assert n == 0
    assert "sin salida" in t
