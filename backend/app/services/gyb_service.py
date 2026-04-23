"""GYB (Got Your Back) wrapper for Gmail backup/restore."""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.google.credentials import load_sa_info


@dataclass(slots=True)
class GybWorkspace:
    sa_json_path: str
    oauth_json_path: str
    local_folder: str


@asynccontextmanager
async def prepare_gyb_workspace(
    db: AsyncSession, *, account_email: str, local_folder: str
) -> AsyncIterator[GybWorkspace]:
    sa_info = await load_sa_info(db)

    tmpdir = tempfile.mkdtemp(prefix="gyb_", dir="/tmp")
    sa_path = str(Path(tmpdir) / "sa.json")
    oauth_path = str(Path(tmpdir) / "oauth2.txt")

    with open(sa_path, "w", encoding="utf-8") as f:
        json.dump(sa_info, f)
    os.chmod(sa_path, 0o600)

    with open(oauth_path, "w", encoding="utf-8") as f:
        f.write(sa_info.get("client_email", ""))
    os.chmod(oauth_path, 0o600)

    Path(local_folder).mkdir(parents=True, exist_ok=True)
    try:
        yield GybWorkspace(sa_path, oauth_path, local_folder)
    finally:
        for p in (sa_path, oauth_path):
            try:
                os.unlink(p)
            except OSError:
                pass


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
        "--service-account",
        "--sa-file", workspace.sa_json_path,
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
) -> tuple[int, str]:
    process = await asyncio.create_subprocess_exec(
        "/usr/local/bin/gyb",
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    assert process.stdout is not None
    collected: list[str] = []

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

    try:
        await asyncio.wait_for(_drain(), timeout=timeout)
    except asyncio.TimeoutError:
        process.kill()
        raise
    rc = await process.wait()
    return rc, "\n".join(collected)
