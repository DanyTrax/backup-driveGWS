"""Fixed-window rate limiting backed by Redis INCR + EXPIRE."""
from __future__ import annotations

import time
from dataclasses import dataclass

from redis.asyncio import Redis

from app.core.redis_client import get_redis


@dataclass(slots=True)
class RateLimitResult:
    allowed: bool
    count: int
    limit: int
    reset_in_seconds: int


async def check_rate_limit(
    key: str,
    limit: int,
    window_seconds: int,
    redis: Redis | None = None,
) -> RateLimitResult:
    """Increment a per-window counter and return whether the caller may proceed."""
    if limit <= 0:
        return RateLimitResult(True, 0, limit, window_seconds)

    redis = redis or get_redis()
    now = int(time.time())
    bucket = now // window_seconds
    redis_key = f"rl:{key}:{bucket}"

    async with redis.pipeline(transaction=True) as pipe:
        pipe.incr(redis_key)
        pipe.expire(redis_key, window_seconds)
        count, _ = await pipe.execute()

    count_int = int(count)
    reset_in = window_seconds - (now % window_seconds)
    return RateLimitResult(
        allowed=count_int <= limit,
        count=count_int,
        limit=limit,
        reset_in_seconds=reset_in,
    )
