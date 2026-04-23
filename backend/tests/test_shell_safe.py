"""Safety checks for the command runner."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("SECRET_KEY", "a" * 40)
os.environ.setdefault("FERNET_KEY", "X4R0fXsPI_dKv-EbN8JxW7zKdOqmRVcAjUPblhMx7eg=")
os.environ.setdefault("POSTGRES_USER", "ci")
os.environ.setdefault("POSTGRES_PASSWORD", "ci")
os.environ.setdefault("POSTGRES_DB", "ci")


def test_rejects_unknown_binary() -> None:
    from app.utils.shell_safe import CommandNotAllowed, safe_run

    with pytest.raises(CommandNotAllowed):
        safe_run("bash", ["-c", "rm -rf /"])


def test_allowlist_contains_expected_tools() -> None:
    from app.utils.shell_safe import ALLOWED_BINARIES

    for name in ("rclone", "gyb", "git", "age", "tar"):
        assert name in ALLOWED_BINARIES
