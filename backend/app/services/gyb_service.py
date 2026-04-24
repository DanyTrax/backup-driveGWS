"""GYB (Got Your Back) wrapper for Gmail backup/restore."""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.backup_batch_registry import is_log_cancelled
from app.services.google.credentials import load_sa_info
from app.utils.async_process import SUBPROCESS_PIPE_LIMIT

# GYB 1.9x lee la clave de servicio desde config_folder/oauth2service.json (--sa-file fue eliminado).


def gyb_executable() -> str:
    """Ruta al binario GYB (imagen Docker o instalación manual)."""
    env = (os.environ.get("GYB_PATH") or "").strip()
    candidates = [env, "/usr/local/bin/gyb", "/opt/gyb/gyb", shutil.which("gyb") or ""]
    for p in candidates:
        if p and os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return "/usr/local/bin/gyb"


@dataclass(slots=True)
class GybWorkspace:
    config_folder: str
    local_folder: str


@asynccontextmanager
async def prepare_gyb_workspace(
    db: AsyncSession, *, account_email: str, local_folder: str
) -> AsyncIterator[GybWorkspace]:
    _ = account_email
    sa_info = await load_sa_info(db)

    tmpdir = tempfile.mkdtemp(prefix="gyb_", dir="/tmp")
    sa_file = Path(tmpdir) / "oauth2service.json"

    try:
        sa_file.write_text(json.dumps(sa_info, ensure_ascii=False, indent=2), encoding="utf-8")
        os.chmod(sa_file, 0o600)

        Path(local_folder).mkdir(parents=True, exist_ok=True)
        yield GybWorkspace(config_folder=tmpdir, local_folder=local_folder)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def build_gyb_argv(
    workspace: GybWorkspace,
    *,
    email: str,
    action: str = "backup",
    search: str | None = None,
    strip_labels: bool = False,
    extra_flags: Iterable[str] = (),
) -> list[str]:
    if action not in {"backup", "restore", "restore-mbox", "estimate", "count"}:
        raise ValueError(f"unsupported gyb action: {action}")
    argv = [
        "--email", email,
        "--action", action,
        "--local-folder", workspace.local_folder,
        "--config-folder", workspace.config_folder,
        "--service-account",
        "--use-admin", email,
    ]
    if search:
        argv += ["--search", search]
    if strip_labels:
        argv.append("--strip-labels")
    argv += list(extra_flags)
    return argv


async def run_gyb(
    argv: list[str],
    *,
    on_line: "callable[[str], None] | None" = None,
    timeout: int | None = None,
    cancel_log_id: str | None = None,
) -> tuple[int, str]:
    process = await asyncio.create_subprocess_exec(
        gyb_executable(),
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        limit=SUBPROCESS_PIPE_LIMIT,
    )
    assert process.stdout is not None
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
            if on_line:
                try:
                    on_line(decoded)
                except Exception:
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
