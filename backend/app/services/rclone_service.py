"""rclone wrapper — builds ephemeral configs and orchestrates runs.

For each account we:
  * Generate a temporary rclone.conf that embeds the Service Account JSON and
    the impersonated subject (Domain-Wide Delegation).
  * Execute `rclone copy` / `sync` against the account's vault sub-folder.
  * Parse `--stats` output into structured progress events.
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator, Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.backup_batch_registry import is_log_cancelled
from app.services.google.credentials import load_sa_info
from app.utils.async_process import SUBPROCESS_PIPE_LIMIT
from app.services.settings_service import (
    KEY_VAULT_ROOT_FOLDER_ID,
    KEY_VAULT_SHARED_DRIVE_ID,
    get_value,
)


@dataclass(slots=True)
class RcloneConfig:
    config_path: str
    remote_source: str
    remote_dest: str
    cleanup_paths: list[str] = field(default_factory=list)


@asynccontextmanager
async def build_rclone_config(
    db: AsyncSession,
    *,
    impersonate_email: str,
    vault_folder_id: str,
) -> AsyncIterator[RcloneConfig]:
    """Materialize a per-account rclone.conf in a secure temp dir."""
    sa_info = await load_sa_info(db)
    team_drive_id = await get_value(db, KEY_VAULT_SHARED_DRIVE_ID)

    tmpdir = tempfile.mkdtemp(prefix="rclone_cfg_", dir="/tmp")
    sa_path = str(Path(tmpdir) / "sa.json")
    cfg_path = str(Path(tmpdir) / "rclone.conf")

    with open(sa_path, "w", encoding="utf-8") as f:
        json.dump(sa_info, f)
    os.chmod(sa_path, 0o600)

    # Remote for the user's Drive (impersonated)
    source_lines = [
        "[source]",
        "type = drive",
        f"service_account_file = {sa_path}",
        f"impersonate = {impersonate_email}",
        "scope = drive",
        "",
    ]
    dest_lines = [
        "[dest]",
        "type = drive",
        f"service_account_file = {sa_path}",
        "scope = drive",
    ]
    if team_drive_id:
        dest_lines.append(f"team_drive = {team_drive_id}")
    dest_lines.append(f"root_folder_id = {vault_folder_id}")
    dest_lines.append("")

    with open(cfg_path, "w", encoding="utf-8") as f:
        f.write("\n".join(source_lines + dest_lines))
    os.chmod(cfg_path, 0o600)

    try:
        yield RcloneConfig(
            config_path=cfg_path,
            remote_source="source:",
            remote_dest="dest:",
            cleanup_paths=[sa_path, cfg_path, tmpdir],
        )
    finally:
        for p in (sa_path, cfg_path):
            try:
                os.unlink(p)
            except OSError:
                pass
        try:
            os.rmdir(tmpdir)
        except OSError:
            pass


def build_rclone_argv(
    cfg: RcloneConfig,
    *,
    mode: str,
    subpath: str | None = None,
    dest_subpath: str | None = None,
    bwlimit: str | None = None,
    dry_run: bool = False,
    extra_flags: Iterable[str] = (),
) -> list[str]:
    """Compose an `argv` list that never touches the shell."""
    if mode not in {"copy", "sync", "check"}:
        raise ValueError(f"unsupported rclone mode: {mode}")

    source = cfg.remote_source
    if subpath:
        source = f"{source}{subpath}"
    dest = cfg.remote_dest
    if dest_subpath:
        dest = f"{cfg.remote_dest.rstrip(':')}:{dest_subpath.lstrip('/')}"
    argv = [
        mode,
        source,
        dest,
        "--config", cfg.config_path,
        "--drive-server-side-across-configs", "false",
        "--stats", "5s",
        "--stats-one-line",
        "--stats-log-level", "NOTICE",
        "--transfers", "4",
        "--checkers", "8",
        "--retries", "3",
        "--low-level-retries", "10",
        "--fast-list",
    ]
    if dry_run:
        argv.append("--dry-run")
    if bwlimit:
        argv += ["--bwlimit", bwlimit]
    argv += list(extra_flags)
    return argv


async def run_rclone(
    argv: list[str],
    *,
    on_line: "callable[[str], None] | None" = None,
    timeout: int | None = None,
    cancel_log_id: str | None = None,
) -> tuple[int, str]:
    """Run rclone streaming stdout so callers can emit progress events."""
    process = await asyncio.create_subprocess_exec(
        "/usr/bin/rclone",
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        limit=SUBPROCESS_PIPE_LIMIT,
    )
    assert process.stdout is not None  # for type-checkers
    collected: list[str] = []
    stop = asyncio.Event()

    async def _watch_cancel() -> None:
        while not stop.is_set():
            if cancel_log_id and await is_log_cancelled(cancel_log_id):
                if process.returncode is None:
                    process.terminate()
                stop.set()
                return
            await asyncio.sleep(0.5)

    watcher = asyncio.create_task(_watch_cancel()) if cancel_log_id else None

    async def _drain() -> None:
        while True:
            line = await process.stdout.readline()  # type: ignore[union-attr]
            if not line:
                break
            decoded = line.decode("utf-8", errors="replace").rstrip()
            collected.append(decoded)
            if on_line is not None:
                try:
                    on_line(decoded)
                except Exception:  # pragma: no cover — progress callbacks must not crash backup
                    pass
            if cancel_log_id and await is_log_cancelled(cancel_log_id):
                if process.returncode is None:
                    process.terminate()
                break

    try:
        await asyncio.wait_for(_drain(), timeout=timeout)
    except asyncio.TimeoutError:
        process.kill()
        raise
    finally:
        stop.set()
        if watcher:
            watcher.cancel()
            with suppress(asyncio.CancelledError):
                await watcher

    if process.returncode is None:
        rc = await process.wait()
    else:
        rc = process.returncode
    return rc, "\n".join(collected)
