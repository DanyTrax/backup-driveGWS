"""Estado publicado en Redis del conteo de ítems de la Shared Drive (panel Mantenimiento / Logs)."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from app.core.redis_client import get_redis

KEY = "host_ops:vault_shared_drive_item_count:status"
TTL_RUNNING_SEC = 7200
TTL_DONE_SEC = 86400 * 7


async def vault_item_count_publish_running(task_id: str) -> None:
    payload = {
        "state": "running",
        "task_id": task_id,
        "started_at": datetime.now(UTC).isoformat(),
        "finished_at": None,
        "result": None,
        "error": None,
    }
    r = get_redis()
    await r.setex(KEY, TTL_RUNNING_SEC, json.dumps(payload, default=str))


async def vault_item_count_publish_success(task_id: str, result: dict[str, Any]) -> None:
    payload = {
        "state": "success",
        "task_id": task_id,
        "started_at": None,
        "finished_at": datetime.now(UTC).isoformat(),
        "result": result,
        "error": None,
    }
    r = get_redis()
    await r.setex(KEY, TTL_DONE_SEC, json.dumps(payload, default=str))


async def vault_item_count_publish_failure(task_id: str, error: str) -> None:
    payload = {
        "state": "failure",
        "task_id": task_id,
        "started_at": None,
        "finished_at": datetime.now(UTC).isoformat(),
        "result": None,
        "error": error[:4000],
    }
    r = get_redis()
    await r.setex(KEY, TTL_DONE_SEC, json.dumps(payload, default=str))


async def vault_item_count_read_session() -> dict[str, Any] | None:
    r = get_redis()
    raw = await r.get(KEY)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None
