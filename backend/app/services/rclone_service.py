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
import shlex
import tempfile
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator, Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
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


def _subprocess_env_for_rclone() -> dict[str, str]:
    """Rclone aplica ``RCLONE_*`` del entorno global; un bwlimit mal formado rompe cualquier invocación."""
    env = dict(os.environ)
    lim = get_settings().rclone_bwlimit.strip()
    if lim:
        env["RCLONE_BWLIMIT"] = lim
    else:
        env.pop("RCLONE_BWLIMIT", None)
    return env


@asynccontextmanager
async def build_rclone_config(
    db: AsyncSession,
    *,
    impersonate_email: str,
    vault_folder_id: str,
    source_root_folder_id: str | None = None,
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

    root_src = (source_root_folder_id or "").strip()
    # Remote for the user's Drive (impersonated)
    source_lines = [
        "[source]",
        "type = drive",
        f"service_account_file = {sa_path}",
        f"impersonate = {impersonate_email}",
        "scope = drive",
    ]
    if root_src:
        source_lines.append(f"root_folder_id = {root_src}")
    source_lines.append("")
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


@asynccontextmanager
async def build_rclone_vault_dest_only_config(
    db: AsyncSession,
    *,
    vault_folder_id: str,
) -> AsyncIterator[RcloneConfig]:
    """Sólo remoto ``dest:`` hacia el vault (Shared Drive + carpeta de cuenta). ``rclone copy`` local→Drive."""
    sa_info = await load_sa_info(db)
    team_drive_id = await get_value(db, KEY_VAULT_SHARED_DRIVE_ID)

    tmpdir = tempfile.mkdtemp(prefix="rclone_dst_", dir="/tmp")
    sa_path = str(Path(tmpdir) / "sa.json")
    cfg_path = str(Path(tmpdir) / "rclone.conf")
    with open(sa_path, "w", encoding="utf-8") as f:
        json.dump(sa_info, f)
    os.chmod(sa_path, 0o600)

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
        f.write("\n".join(dest_lines))
    os.chmod(cfg_path, 0o600)
    try:
        yield RcloneConfig(
            config_path=cfg_path,
            remote_source="",
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


def _gmail_vault_compare_argv_part(s: Settings) -> list[str]:
    out: list[str] = []
    if s.rclone_gmail_vault_compare == "size_only":
        out.append("--size-only")
    elif s.rclone_gmail_vault_compare == "checksum":
        out.append("--checksum")
    return out


def _gmail_vault_tps_argv_part(s: Settings) -> list[str]:
    out: list[str] = []
    lim = s.rclone_gmail_vault_tpslimit
    if lim > 0:
        out += ["--tpslimit", str(lim)]
        burst = s.rclone_gmail_vault_tpslimit_burst
        if burst > 0:
            out += ["--tpslimit-burst", str(burst)]
    return out


def _gmail_vault_extra_flags_argv_part(s: Settings) -> list[str]:
    raw = (s.rclone_gmail_vault_extra_flags or "").strip()
    if not raw:
        return []
    return shlex.split(raw)


def build_rclone_local_to_vault_argv(
    local_abs: str,
    cfg: RcloneConfig,
    *,
    dest_subpath: str,
    dry_run: bool = False,
    extra_flags: Iterable[str] = (),
) -> list[str]:
    """``rclone copy <local> dest:<ruta>`` hacia un vault de cuenta (sin remoto de origen Google)."""
    s = get_settings()
    transfers = s.rclone_gmail_vault_transfers
    checkers = s.rclone_gmail_vault_checkers
    rel = dest_subpath.strip().lstrip("/")
    remote = f"{cfg.remote_dest.rstrip(':')}:{rel}/" if rel else cfg.remote_dest
    argv = [
        "copy",
        str(Path(local_abs).resolve()),
        remote,
        "--config",
        cfg.config_path,
        "--stats",
        "5s",
        "--stats-one-line",
        "--stats-log-level",
        "NOTICE",
        "--transfers",
        str(transfers),
        "--checkers",
        str(checkers),
        "--fast-list",
        "--retries",
        "3",
        "--low-level-retries",
        "10",
    ]
    if s.rclone_gmail_vault_no_traverse:
        argv.append("--no-traverse")
    argv += _gmail_vault_tps_argv_part(s)
    argv += _gmail_vault_compare_argv_part(s)
    argv += _gmail_vault_extra_flags_argv_part(s)
    if dry_run:
        argv.append("--dry-run")
    argv += list(extra_flags)
    return argv


def build_rclone_mkdir_dest_argv(
    cfg: RcloneConfig,
    *,
    dest_subpath: str,
) -> list[str]:
    """``rclone mkdir dest:<ruta>`` — recrea la jerarquía en el vault si alguien borró ``1-GMAIL/`` etc."""
    rel = dest_subpath.strip().strip("/")
    remote = f"{cfg.remote_dest.rstrip(':')}:{rel}" if rel else cfg.remote_dest.rstrip(":").rstrip(":")
    return [
        "mkdir",
        remote,
        "--config",
        cfg.config_path,
        "--retries",
        "3",
        "--low-level-retries",
        "10",
    ]


def build_rclone_check_local_vault_argv(
    local_abs: str,
    cfg: RcloneConfig,
    *,
    dest_subpath: str,
) -> list[str]:
    """``rclone check <local> dest:<ruta> --one-way`` — confirma que lo subido al vault cubre el árbol local."""
    s = get_settings()
    rel = dest_subpath.strip().lstrip("/")
    remote = f"{cfg.remote_dest.rstrip(':')}:{rel}/" if rel else cfg.remote_dest
    argv = [
        "check",
        str(Path(local_abs).resolve()),
        remote,
        "--config",
        cfg.config_path,
        "--checkers",
        str(s.rclone_gmail_vault_checkers),
        "--one-way",
        "--max-backlog",
        "200000",
        "--fast-list",
    ]
    argv += _gmail_vault_compare_argv_part(s)
    argv += _gmail_vault_tps_argv_part(s)
    argv += _gmail_vault_extra_flags_argv_part(s)
    return argv


@asynccontextmanager
async def build_rclone_source_only_config(
    db: AsyncSession,
    *,
    impersonate_email: str,
) -> AsyncIterator[RcloneConfig]:
    """Solo remoto ``source:`` (Mi unidad del usuario vía DWD). Para pruebas ``rclone about``."""
    sa_info = await load_sa_info(db)
    tmpdir = tempfile.mkdtemp(prefix="rclone_src_", dir="/tmp")
    sa_path = str(Path(tmpdir) / "sa.json")
    cfg_path = str(Path(tmpdir) / "rclone.conf")
    with open(sa_path, "w", encoding="utf-8") as f:
        json.dump(sa_info, f)
    os.chmod(sa_path, 0o600)
    source_lines = [
        "[source]",
        "type = drive",
        f"service_account_file = {sa_path}",
        f"impersonate = {impersonate_email}",
        "scope = drive",
        "",
    ]
    with open(cfg_path, "w", encoding="utf-8") as f:
        f.write("\n".join(source_lines))
    os.chmod(cfg_path, 0o600)
    try:
        yield RcloneConfig(
            config_path=cfg_path,
            remote_source="source:",
            remote_dest="source:",
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
    compare_dest_remotes: list[str] | None = None,
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
        # No usar ``--drive-server-side-across-configs`` con valor en otro token: rclone reciente
        # interpreta ese ``false`` como 3.er argumento de copy. El default en Drive es false → omitimos el flag.
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
    if compare_dest_remotes:
        for cr in compare_dest_remotes:
            s = (cr or "").strip()
            if s:
                argv.extend(["--compare-dest", s])
    argv += list(extra_flags)
    return argv


async def rclone_verify_remote_dir(
    cfg: RcloneConfig,
    *,
    path_under_source: str,
    cancel_log_id: str | None = None,
    timeout: int = 90,
) -> tuple[bool, str]:
    """Comprueba que exista y sea listable ``source:<path>`` (p. ej. carpeta ``Computadoras``).

    Usa ``lsd`` con profundidad mínima: carpeta vacía sigue dando rc 0.
    """
    name = path_under_source.strip().strip("/")
    if not name:
        return True, ""
    remote = f"{cfg.remote_source.rstrip(':')}:{name}"
    argv = [
        "lsd",
        remote,
        "--config",
        cfg.config_path,
        "--max-depth",
        "1",
    ]
    rc, out = await run_rclone(argv, on_line=None, timeout=timeout, cancel_log_id=cancel_log_id)
    return rc == 0, out


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
        env=_subprocess_env_for_rclone(),
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
