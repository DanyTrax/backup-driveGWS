"""Operaciones opcionales sobre el Docker del host y despliegue de la pila.

Requiere en producción:
  * ``host_docker_control_enabled`` / ``host_stack_deploy_enabled`` en Settings.
  * Montaje del socket: ``/var/run/docker.sock`` (típicamente rw).
  * Para despliegue: montar el repo del stack en **la misma ruta** en host y contenedor
    (p. ej. ``/opt/stacks/backup-stack:/opt/stacks/backup-stack``) para que el daemon
    resuelva bien el contexto de ``docker compose build``.
  * Usuario del proceso con GID compatible con el socket (p. ej. ``group_add`` del GID ``docker`` del host).
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.schemas.host_ops import HostOpsScheduleIn
from app.services.settings_service import get_json, set_json
from app.utils.shell_safe import RunResult, safe_run

KEY_DOCKER_PRUNE_SCHEDULE = "host.docker_prune_schedule"

_DOCKER_COMPOSE_FILE = "docker-compose.yml"


def _settings_ok_docker() -> tuple[bool, str | None]:
    s = get_settings()
    if not s.host_docker_control_enabled:
        return False, "host_docker_control_disabled"
    sock = Path(s.host_docker_socket_path)
    if not sock.exists():
        return False, "docker_socket_missing"
    return True, None


def _settings_ok_deploy() -> tuple[bool, str | None]:
    s = get_settings()
    if not s.host_stack_deploy_enabled:
        return False, "host_stack_deploy_disabled"
    ok, err = _settings_ok_docker()
    if not ok:
        return False, err
    if not (s.host_stack_mount_path or "").strip():
        return False, "host_stack_mount_path_missing"
    compose_dir = Path(s.host_stack_mount_path) / s.host_compose_project_subdir
    if not (compose_dir / _DOCKER_COMPOSE_FILE).is_file():
        return False, "compose_file_missing"
    env_path = (compose_dir / Path(s.host_compose_env_file)).resolve()
    if not env_path.is_file():
        return False, "compose_env_file_missing"
    return True, None


def _tail(s: str, n: int = 6000) -> str:
    if len(s) <= n:
        return s
    return s[-n:]


def run_docker_prune(
    preset: Literal["light", "deep"],
) -> dict[str, Any]:
    ok, err = _settings_ok_docker()
    if not ok:
        return {"ok": False, "error": err}
    steps: list[dict[str, Any]] = []

    r1 = safe_run("docker", ["system", "prune", "-f"], timeout=600)
    steps.append(
        {"cmd": "docker system prune -f", "rc": r1.returncode, "stderr_tail": _tail(r1.stderr)}
    )
    if r1.returncode != 0:
        return {"ok": False, "error": "docker_system_prune_failed", "steps": steps}

    if preset == "deep":
        r2 = safe_run("docker", ["image", "prune", "-a", "-f"], timeout=3600)
        steps.append(
            {
                "cmd": "docker image prune -a -f",
                "rc": r2.returncode,
                "stderr_tail": _tail(r2.stderr),
            }
        )
        if r2.returncode != 0:
            return {"ok": False, "error": "docker_image_prune_failed", "steps": steps}

        r3 = safe_run("docker", ["builder", "prune", "-af"], timeout=3600)
        steps.append(
            {
                "cmd": "docker builder prune -af",
                "rc": r3.returncode,
                "stderr_tail": _tail(r3.stderr),
            }
        )
        # buildkit puede no existir: no fallar el job completo
        if r3.returncode != 0:
            steps[-1]["note"] = "builder_prune_nonzero_ignored"

    return {"ok": True, "preset": preset, "steps": steps}


def run_stack_deploy(mode: Literal["frontend", "frontend_backend", "rebuild_app", "full"]) -> dict[str, Any]:
    ok, err = _settings_ok_deploy()
    if not ok:
        return {"ok": False, "error": err}
    s = get_settings()
    stack = Path(s.host_stack_mount_path).resolve()
    compose_dir = (stack / s.host_compose_project_subdir).resolve()
    env_file = (compose_dir / Path(s.host_compose_env_file)).resolve()
    env = {**os.environ, "COMPOSE_PROJECT_DIR": str(compose_dir)}

    def _compose(args: list[str], timeout: int = 7200) -> RunResult:
        base = [
            "compose",
            "-f",
            _DOCKER_COMPOSE_FILE,
            "--env-file",
            str(env_file),
            *args,
        ]
        return safe_run("docker", base, cwd=str(compose_dir), timeout=timeout, env=env)

    steps: list[dict[str, Any]] = []

    if mode == "full":
        git_root = Path(s.host_git_path).resolve() if (s.host_git_path or "").strip() else stack
        r0 = safe_run("git", ["-C", str(git_root), "pull", "--ff-only"], timeout=900)
        steps.append(
            {
                "cmd": f"git -C {git_root} pull --ff-only",
                "rc": r0.returncode,
                "stderr_tail": _tail(r0.stderr),
            }
        )
        if r0.returncode != 0:
            return {"ok": False, "error": "git_pull_failed", "steps": steps}

        r_build = _compose(["build"], timeout=7200)
        steps.append(
            {
                "cmd": "docker compose build",
                "rc": r_build.returncode,
                "stderr_tail": _tail(r_build.stderr),
            }
        )
        if r_build.returncode != 0:
            return {"ok": False, "error": "compose_build_failed", "steps": steps}

        r_up = _compose(["up", "-d"], timeout=1200)
        steps.append(
            {
                "cmd": "docker compose up -d",
                "rc": r_up.returncode,
                "stderr_tail": _tail(r_up.stderr),
            }
        )
        if r_up.returncode != 0:
            return {"ok": False, "error": "compose_up_failed", "steps": steps}
        return {"ok": True, "mode": mode, "steps": steps}

    if mode == "rebuild_app":
        r = _compose(["build", "app"], timeout=7200)
        steps.append(
            {
                "cmd": "docker compose build app",
                "rc": r.returncode,
                "stderr_tail": _tail(r.stderr),
            }
        )
        if r.returncode != 0:
            return {"ok": False, "error": "compose_build_app_failed", "steps": steps}
        return {"ok": True, "mode": mode, "steps": steps}

    if mode == "frontend":
        r1 = _compose(["build", "app"], timeout=7200)
        steps.append(
            {
                "cmd": "docker compose build app",
                "rc": r1.returncode,
                "stderr_tail": _tail(r1.stderr),
            }
        )
        if r1.returncode != 0:
            return {"ok": False, "error": "compose_build_app_failed", "steps": steps}
        r2 = _compose(["up", "-d", "--no-deps", "app"], timeout=600)
        steps.append(
            {
                "cmd": "docker compose up -d --no-deps app",
                "rc": r2.returncode,
                "stderr_tail": _tail(r2.stderr),
            }
        )
        if r2.returncode != 0:
            return {"ok": False, "error": "compose_up_app_failed", "steps": steps}
        return {"ok": True, "mode": mode, "steps": steps}

    # frontend_backend
    r1 = _compose(["build", "app", "worker", "beat"], timeout=7200)
    steps.append(
        {
            "cmd": "docker compose build app worker beat",
            "rc": r1.returncode,
            "stderr_tail": _tail(r1.stderr),
        }
    )
    if r1.returncode != 0:
        return {"ok": False, "error": "compose_build_failed", "steps": steps}
    r2 = _compose(["up", "-d", "--no-deps", "app", "worker", "beat"], timeout=900)
    steps.append(
        {
            "cmd": "docker compose up -d --no-deps app worker beat",
            "rc": r2.returncode,
            "stderr_tail": _tail(r2.stderr),
        }
    )
    if r2.returncode != 0:
        return {"ok": False, "error": "compose_up_failed", "steps": steps}
    return {"ok": True, "mode": mode, "steps": steps}


def _dow_sunday0(dt: datetime) -> int:
    return (dt.weekday() + 1) % 7


async def get_prune_schedule(db: AsyncSession) -> dict[str, Any]:
    raw = await get_json(db, KEY_DOCKER_PRUNE_SCHEDULE)
    if not isinstance(raw, dict):
        raw = {}
    return {
        "enabled": bool(raw.get("enabled")),
        "preset": raw.get("preset") if raw.get("preset") in ("light", "deep") else "deep",
        "hour": int(raw.get("hour", 4)),
        "minute": int(raw.get("minute", 10)),
        "dow": raw.get("dow") if raw.get("dow") is None or raw.get("dow") in range(7) else None,
        "last_run_date": raw.get("last_run_date"),
    }


async def save_prune_schedule(db: AsyncSession, data: HostOpsScheduleIn) -> dict[str, Any]:
    prev = await get_prune_schedule(db)
    merged = {
        "enabled": data.enabled,
        "preset": data.preset,
        "hour": data.hour,
        "minute": data.minute,
        "dow": data.dow,
        "last_run_date": prev.get("last_run_date"),
    }
    await set_json(db, KEY_DOCKER_PRUNE_SCHEDULE, merged, category="host_ops")
    await db.commit()
    return merged


async def maybe_run_scheduled_docker_prune(db: AsyncSession) -> dict[str, Any]:
    cfg = await get_prune_schedule(db)
    if not cfg.get("enabled"):
        return {"ran": False, "reason": "disabled"}
    ok, err = _settings_ok_docker()
    if not ok:
        return {"ran": False, "reason": err}

    s = get_settings()
    now = datetime.now(ZoneInfo(s.tz))
    if now.minute % 5 != 0:
        return {"ran": False, "reason": "not_tick_minute"}

    h, m = int(cfg["hour"]), int(cfg["minute"])
    if now.hour != h or not (m <= now.minute < m + 5):
        return {"ran": False, "reason": "not_slot"}

    dow = cfg.get("dow")
    if dow is not None and _dow_sunday0(now) != int(dow):
        return {"ran": False, "reason": "wrong_weekday"}

    today = now.date().isoformat()
    if cfg.get("last_run_date") == today:
        return {"ran": False, "reason": "already_ran_today"}

    preset = cfg["preset"] if cfg["preset"] in ("light", "deep") else "deep"
    result = run_docker_prune(preset)
    merged = {**cfg, "last_run_date": today if result.get("ok") else cfg.get("last_run_date")}
    await set_json(db, KEY_DOCKER_PRUNE_SCHEDULE, merged, category="host_ops")
    await db.commit()
    return {"ran": True, "result": result}


def host_ops_public_config() -> dict[str, Any]:
    s = get_settings()
    stack = (s.host_stack_mount_path or "").strip()
    compose_dir = None
    if stack:
        p = Path(stack) / s.host_compose_project_subdir
        if p.is_dir():
            compose_dir = str(p)
    return {
        "docker_control_enabled": s.host_docker_control_enabled,
        "stack_deploy_enabled": s.host_stack_deploy_enabled,
        "docker_socket_present": Path(s.host_docker_socket_path).exists(),
        "stack_path_configured": bool(stack),
        "compose_dir": compose_dir,
    }
