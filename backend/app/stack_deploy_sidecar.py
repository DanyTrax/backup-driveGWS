"""Ejecutado dentro de un contenedor efímero ``docker run`` (no forma parte del compose).

Escribe un marcador y un JSON en stdout para que la API pueda parsear el resultado
tras ``docker logs``, aunque el contenedor ``app`` se reinicie durante el despliegue.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import cast

from app.services.host_ops_service import DEPLOY_RESULT_MARKER, StackDeployMode, run_stack_deploy_with_paths

_VALID = frozenset({"frontend", "frontend_backend", "rebuild_app", "full"})


def main() -> None:
    mode = os.environ.get("MSA_STACK_DEPLOY_MODE", "")
    if mode not in _VALID:
        err = {"ok": False, "error": "bad_deploy_mode", "steps": []}
        print(DEPLOY_RESULT_MARKER, flush=True)
        print(json.dumps(err, ensure_ascii=False), flush=True)
        sys.exit(1)
    stack = Path(os.environ.get("HOST_STACK_MOUNT_PATH", "").strip())
    sub = (os.environ.get("HOST_COMPOSE_PROJECT_SUBDIR") or "docker").strip()
    env_f = (os.environ.get("HOST_COMPOSE_ENV_FILE") or "../.env").strip()
    git_p = (os.environ.get("HOST_GIT_PATH") or "").strip()
    try:
        result = run_stack_deploy_with_paths(
            cast(StackDeployMode, mode),
            stack_mount=stack,
            compose_subdir=sub,
            compose_env_file=env_f,
            git_path=git_p,
        )
    except Exception as e:
        result = {"ok": False, "error": f"sidecar_exception:{e!s}", "steps": []}
    print(DEPLOY_RESULT_MARKER, flush=True)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    sys.exit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()
