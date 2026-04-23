"""Liveness / readiness endpoints used by Docker, NPM, and monitoring."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.core.config import get_settings
from app.core.database import get_db

router = APIRouter()


@router.get("/health", status_code=status.HTTP_200_OK, summary="Liveness probe")
async def health():
    s = get_settings()
    return {
        "status": "ok",
        "app": s.app_name,
        "version": __version__,
        "env": s.app_env,
        "time": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/health/ready", summary="Readiness probe (DB check)")
async def ready(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ready", "db": "ok"}
    except Exception as exc:  # pragma: no cover
        return {"status": "degraded", "db": str(exc)}
