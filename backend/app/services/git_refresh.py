"""Git refresh utility for bind-mount deployments."""
from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from app.core.config import get_settings


async def pull_and_status(repo_path: Path) -> dict:
    settings = get_settings()
    branch = settings.git_branch or "main"
    cmds = [
        ["git", "-C", str(repo_path), "fetch", "--prune"],
        ["git", "-C", str(repo_path), "checkout", branch],
        ["git", "-C", str(repo_path), "reset", "--hard", f"origin/{branch}"],
    ]
    outputs: list[dict] = []
    for argv in cmds:
        proc = await asyncio.to_thread(
            subprocess.run, argv, capture_output=True, text=True, check=False
        )
        outputs.append(
            {
                "cmd": " ".join(argv),
                "rc": proc.returncode,
                "stdout": proc.stdout[-4000:],
                "stderr": proc.stderr[-4000:],
            }
        )
        if proc.returncode != 0:
            return {"ok": False, "steps": outputs}
    sha_proc = await asyncio.to_thread(
        subprocess.run,
        ["git", "-C", str(repo_path), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "ok": True,
        "steps": outputs,
        "head": sha_proc.stdout.strip(),
    }
