"""Heurísticas de duración aproximada para encolar backups (no son SLAs)."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accounts import GwAccount
from app.models.enums import BackupScope, BackupStatus
from app.models.tasks import BackupLog, BackupTask


def _mb_per_sec_optimistic() -> float:
    return 3.0


def _mb_per_sec_pessimistic() -> float:
    return 0.25


def _bytes_to_minute_range(nbytes: int) -> tuple[int, int] | None:
    if nbytes <= 0:
        return None
    mb = nbytes / (1024 * 1024)
    mopt = int(max(1, (mb / _mb_per_sec_optimistic()) / 60))
    mpes = int(max(1, (mb / _mb_per_sec_pessimistic()) / 60))
    if mopt > mpes:
        mopt, mpes = mpes, mopt
    return mopt, mpes


def _messages_to_minute_range(n: int) -> tuple[int, int] | None:
    if n <= 0:
        return None
    # Muy aprox: 5–40 ms/msg API+GYB+red
    mmin = int(max(1, n * 0.05 / 60))
    mmax = int(max(1, n * 0.4 / 60))
    if mmin > mmax:
        mmin, mmax = mmax, mmin
    return mmin, mmax


async def _last_drive_bytes_moved(
    db: AsyncSession, account_id: uuid.UUID, *, scopes: tuple[str, ...]
) -> int | None:
    """Bytes transferidos en la última ejecución Drive exitosa (proxy de tamaño a mover)."""
    stmt = (
        select(BackupLog.bytes_transferred)
        .where(
            BackupLog.account_id == account_id,
            BackupLog.status == BackupStatus.SUCCESS.value,
            BackupLog.scope.in_(scopes),
        )
        .order_by(BackupLog.finished_at.desc().nullslast())
        .limit(1)
    )
    v = (await db.execute(stmt)).scalar_one_or_none()
    return int(v) if v is not None else None


async def run_estimate_payload(db: AsyncSession, task: BackupTask) -> dict[str, Any]:
    """Devuelve dict serializable para GET /tasks/{id}/run-estimate."""
    accounts = [a for a in (task.accounts or []) if a.is_backup_enabled]
    scope = task.scope
    items: list[dict[str, Any]] = []
    want_gmail = scope in (BackupScope.GMAIL.value, BackupScope.FULL.value)
    want_drive = scope in (
        BackupScope.DRIVE_ROOT.value,
        BackupScope.DRIVE_COMPUTADORAS.value,
        BackupScope.FULL.value,
    )
    drive_scopes = (BackupScope.DRIVE_ROOT.value, BackupScope.DRIVE_COMPUTADORAS.value)

    for acc in accounts:
        gpart: dict[str, Any] | None = None
        dpart: dict[str, Any] | None = None
        if want_gmail:
            b = acc.total_bytes_cache
            m = acc.total_messages_cache
            r = _bytes_to_minute_range(b) if b and b > 0 else _messages_to_minute_range(m or 0)
            if r:
                gpart = {
                    "min_minutes": r[0],
                    "max_minutes": r[1],
                    "basis": (
                        f"~{b / (1024**2):.1f} MB en último backup local (Maildir)"
                        if b and b > 0
                        else f"~{m} mensajes en caché (sin bytes fiables)"
                    ),
                }
            else:
                gpart = {
                    "min_minutes": None,
                    "max_minutes": None,
                    "basis": "Sin historial aún: primera copia depende del buzón en Google.",
                }
        if want_drive:
            lastb = await _last_drive_bytes_moved(db, acc.id, scopes=drive_scopes)
            r = _bytes_to_minute_range(lastb) if lastb else None
            if r:
                dpart = {
                    "min_minutes": r[0],
                    "max_minutes": r[1],
                    "basis": f"Última corrida Drive exitosa movió ~{lastb / (1024**2):.1f} MB",
                }
            else:
                dpart = {
                    "min_minutes": None,
                    "max_minutes": None,
                    "basis": "Sin corrida Drive previa o sin bytes registrados; el primer sync puede ser largo.",
                }
        if gpart is not None or dpart is not None:
            items.append({"email": acc.email, "gmail": gpart, "drive": dpart})

    total_min, total_max = 0, 0
    have_any = False
    for it in items:
        for k in ("gmail", "drive"):
            p = it.get(k)
            if not p or p.get("min_minutes") is None:
                continue
            total_min += int(p["min_minutes"])
            total_max += int(p["max_minutes"])
            have_any = True

    return {
        "task_id": str(task.id),
        "scope": task.scope,
        "mode": task.mode,
        "items": items,
        "sum_minutes_min": total_min if have_any else None,
        "sum_minutes_max": total_max if have_any else None,
        "disclaimer": (
            "Aproximación según datos locales y última corrida; red, Google y "
            "disco varían. No incluye cola de otros jobs ni límite de paralelismo."
        ),
    }
