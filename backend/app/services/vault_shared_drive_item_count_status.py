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
    tid = str(task_id or "").strip()
    if not tid:
        raise ValueError("vault_item_count_publish_running requires non-empty task_id")
    now = datetime.now(UTC).isoformat()
    payload = {
        "state": "running",
        "task_id": tid,
        "started_at": now,
        "finished_at": None,
        "result": None,
        "error": None,
        "progress_items": 0,
        "pages_fetched": 0,
        "progress_updated_at": now,
    }
    r = get_redis()
    await r.setex(KEY, TTL_RUNNING_SEC, json.dumps(payload, default=str))


async def vault_item_count_publish_success(task_id: str, result: dict[str, Any]) -> None:
    r = get_redis()
    started_at: str | None = None
    raw = await r.get(KEY)
    if raw:
        try:
            prev = json.loads(raw)
            if str(prev.get("task_id") or "") == task_id and prev.get("started_at"):
                started_at = str(prev["started_at"])
        except json.JSONDecodeError:
            pass
    payload = {
        "state": "success",
        "task_id": task_id,
        "started_at": started_at,
        "finished_at": datetime.now(UTC).isoformat(),
        "result": result,
        "error": None,
        "progress_items": None,
        "pages_fetched": None,
        "progress_updated_at": None,
    }
    await r.setex(KEY, TTL_DONE_SEC, json.dumps(payload, default=str))


async def vault_item_count_publish_failure(task_id: str, error: str) -> None:
    r = get_redis()
    started_at: str | None = None
    progress_items: int | None = None
    pages_fetched: int | None = None
    progress_updated_at: str | None = None
    raw = await r.get(KEY)
    if raw:
        try:
            prev = json.loads(raw)
            ptid = str(prev.get("task_id") or "")
            if ptid == task_id and prev.get("started_at"):
                started_at = str(prev["started_at"])
            if ptid == task_id:
                if prev.get("progress_items") is not None:
                    try:
                        progress_items = int(prev["progress_items"])
                    except (TypeError, ValueError):
                        progress_items = None
                if prev.get("pages_fetched") is not None:
                    try:
                        pages_fetched = int(prev["pages_fetched"])
                    except (TypeError, ValueError):
                        pages_fetched = None
                pu = prev.get("progress_updated_at")
                if pu:
                    progress_updated_at = str(pu)
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    payload = {
        "state": "failure",
        "task_id": task_id,
        "started_at": started_at,
        "finished_at": datetime.now(UTC).isoformat(),
        "result": None,
        "error": error[:4000],
        "progress_items": progress_items,
        "pages_fetched": pages_fetched,
        "progress_updated_at": progress_updated_at,
    }
    await r.setex(KEY, TTL_DONE_SEC, json.dumps(payload, default=str))


async def vault_item_count_update_running_progress(*, items: int, pages_fetched: int) -> None:
    """Actualiza contadores parciales mientras el worker pagina la API de Drive."""
    r = get_redis()
    raw = await r.get(KEY)
    if not raw:
        return
    try:
        cur = json.loads(raw)
    except json.JSONDecodeError:
        return
    if cur.get("state") != "running":
        return
    now = datetime.now(UTC).isoformat()
    cur["progress_items"] = int(items)
    cur["pages_fetched"] = int(pages_fetched)
    cur["progress_updated_at"] = now
    await r.setex(KEY, TTL_RUNNING_SEC, json.dumps(cur, default=str))


async def vault_item_count_read_session() -> dict[str, Any] | None:
    r = get_redis()
    raw = await r.get(KEY)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None
