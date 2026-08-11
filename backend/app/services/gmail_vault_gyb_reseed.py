"""Filtro Gmail (--search) tras purga del workdir: solo desde último sellado ZIP."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


def overlap_days_from_filters(filters: dict[str, Any] | None) -> int:
    v = (filters or {}).get("overlap_days", 1)
    try:
        return max(0, min(int(v), 366))
    except (TypeError, ValueError):
        return 1


def gyb_workdir_needs_date_reseed(work_root: Path) -> bool:
    """True si no hay export .eml/.mbox: GYB no puede ser incremental solo con estado local."""
    if not work_root.is_dir():
        return True
    for p in work_root.rglob("*"):
        if p.is_file() and p.suffix.lower() in (".eml", ".mbox"):
            return False
    return True


def sealed_fetch_start_date(
    last_sealed_at: datetime,
    *,
    overlap_days: int,
    task_timezone: str,
) -> date:
    """Primer día civil (TZ tarea) a incluir: sellado − overlap_days."""
    tz_name = (task_timezone or "UTC").strip() or "UTC"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")
    sealed_local = last_sealed_at.astimezone(tz).date()
    days = max(0, min(int(overlap_days), 366))
    return sealed_local - timedelta(days=days)


def gmail_search_after_sealed(
    last_sealed_at: datetime,
    *,
    overlap_days: int = 1,
    task_timezone: str = "UTC",
) -> str:
    """Query Gmail para GYB ``--search``: mensajes desde (sellado − overlap), inclusive.

    Gmail ``after:YYYY/MM/DD`` es exclusivo de esa fecha → restamos un día al inicio inclusivo.
    """
    start = sealed_fetch_start_date(
        last_sealed_at,
        overlap_days=overlap_days,
        task_timezone=task_timezone,
    )
    exclusive = start - timedelta(days=1)
    return f"after:{exclusive.year}/{exclusive.month:02d}/{exclusive.day:02d}"


def resolve_gyb_search_after_workdir_purge(
    *,
    work_root: Path,
    last_sealed_at: datetime | None,
    filters: dict | None,
    task_timezone: str,
) -> str | None:
    """Si el workdir está vacío y hay sellado ZIP, limita GYB al tramo post-sellado.

    Sin sellado → None (full GYB / bootstrap).
    Con export local → None (incremental nativo de GYB sobre disco).
    """
    if last_sealed_at is None:
        return None
    if not gyb_workdir_needs_date_reseed(work_root):
        return None
    overlap = overlap_days_from_filters(filters)
    return gmail_search_after_sealed(
        last_sealed_at,
        overlap_days=overlap,
        task_timezone=task_timezone,
    )
