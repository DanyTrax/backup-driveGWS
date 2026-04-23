"""Helpers to bridge Celery (sync) <-> async SQLAlchemy sessions."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal

T = TypeVar("T")


def run_async(coro: Awaitable[T]) -> T:
    """Run an async coroutine from sync code, making sure we always have a loop."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    if loop.is_running():  # pragma: no cover
        # Celery workers are sync; a running loop here would be unexpected.
        raise RuntimeError("run_async called while event loop is already running")
    return loop.run_until_complete(coro)


@asynccontextmanager
async def async_session() -> AsyncSession:  # type: ignore[misc]
    async with AsyncSessionLocal() as session:
        yield session


async def with_session(
    func: Callable[[AsyncSession], Awaitable[T]],
) -> T:
    async with AsyncSessionLocal() as session:
        try:
            result = await func(session)
            await session.commit()
            return result
        except Exception:
            await session.rollback()
            raise
