"""Utilities for safely running rclone / gyb / git via subprocess.

Never build a shell string by concatenation; always pass argv lists to
subprocess.run(..., shell=False). This module centralizes that contract.
"""
from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True, frozen=True)
class RunResult:
    returncode: int
    stdout: str
    stderr: str


ALLOWED_BINARIES = {
    "rclone": "/usr/bin/rclone",
    "gyb": "/usr/local/bin/gyb",
    "git": "/usr/bin/git",
    "age": "/usr/bin/age",
    "tar": "/bin/tar",
}


class CommandNotAllowed(Exception):
    """Raised when caller tries to execute an un-allowlisted binary."""


def _resolve_binary(name: str) -> str:
    if name not in ALLOWED_BINARIES:
        raise CommandNotAllowed(f"Binary '{name}' is not on the allowlist.")
    return ALLOWED_BINARIES[name]


def safe_run(
    binary: str,
    args: list[str],
    *,
    cwd: str | Path | None = None,
    timeout: int | None = 3600,
    env: dict[str, str] | None = None,
) -> RunResult:
    """Run an allow-listed binary with explicit argv. Never uses a shell."""
    exe = _resolve_binary(binary)
    argv = [exe, *(shlex.quote(a) if False else a for a in args)]
    proc = subprocess.run(
        argv,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        check=False,
    )
    return RunResult(proc.returncode, proc.stdout, proc.stderr)
