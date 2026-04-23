"""Redis pub/sub bridge for real-time backup progress events."""
from __future__ import annotations

import json
from typing import Any, AsyncIterator

from redis.asyncio import Redis

from app.core.redis_client import get_redis

CHANNEL_PREFIX = "progress:"


def _channel(log_id: str) -> str:
    return f"{CHANNEL_PREFIX}{log_id}"


async def publish(log_id: str, event: dict[str, Any], *, redis: Redis | None = None) -> None:
    redis = redis or get_redis()
    payload = json.dumps(event, default=str, ensure_ascii=False)
    await redis.publish(_channel(log_id), payload)
    await redis.setex(f"progress:last:{log_id}", 3600, payload)


async def last_event(log_id: str, *, redis: Redis | None = None) -> dict[str, Any] | None:
    redis = redis or get_redis()
    raw = await redis.get(f"progress:last:{log_id}")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def subscribe(log_id: str, *, redis: Redis | None = None) -> AsyncIterator[dict[str, Any]]:
    redis = redis or get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(_channel(log_id))
    try:
        async for message in pubsub.listen():
            if message is None or message.get("type") != "message":
                continue
            data = message.get("data")
            if not data:
                continue
            try:
                yield json.loads(data)
            except json.JSONDecodeError:
                continue
    finally:
        try:
            await pubsub.unsubscribe(_channel(log_id))
        finally:
            await pubsub.close()
