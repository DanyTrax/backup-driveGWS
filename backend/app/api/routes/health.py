"""Liveness / readiness endpoints used by Docker, NPM, and monitoring."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.core.config import get_settings
from app.core.database import get_db
from app.core.redis_client import get_redis

router = APIRouter()


@router.get("/health", status_code=status.HTTP_200_OK, summary="Liveness probe")
async def health():
    s = get_settings()
    return {
        "status": "ok",
        "app": s.app_name,
        "version": __version__,
        "env": s.app_env,
        "time": datetime.now(ZoneInfo(s.tz)).isoformat(),
    }


@router.get("/health/ready", summary="Readiness probe (DB + Redis; SSO requiere Redis ok)")
async def ready(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        db_s = "ok"
    except Exception as exc:  # pragma: no cover
        return {"status": "degraded", "db": str(exc), "redis": "skipped"}

    try:
        r = get_redis()
        await r.ping()
        redis_s: str = "ok"
    except Exception as exc:  # pragma: no cover
        redis_s = f"error: {exc!s}"[:500]

    return {
        "status": "ready" if redis_s == "ok" else "degraded",
        "db": db_s,
        "redis": redis_s,
    }
