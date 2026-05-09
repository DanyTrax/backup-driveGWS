"""Decide si en esta corrida corresponde subir un ZIP al vault (Fase 3).

Convención ``vault_anchor_dow``: igual que ``datetime.weekday()`` en la TZ de la tarea (lunes=0 … domingo=6).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Optional
from zoneinfo import ZoneInfo

from app.services.gmail_vault_zip_layout import ZipCadenceDir, seal_kind_to_zip_cadence_dir


@dataclass(frozen=True)
class GmailZipUploadDecision:
    should_upload: bool
    period_start: date
    period_end: date
    seal_kind: str  # bootstrap | weekly | monthly | manual
    cadence_dir: ZipCadenceDir
    reason: str


def _filters_int(filters: dict[str, Any], key: str, default: int) -> int:
    v = filters.get(key)
    if v is None:
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _filters_bool(filters: dict[str, Any], key: str, default: bool) -> bool:
    v = filters.get(key)
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on")
    return bool(v)


def resolve_gmail_zip_upload_plan(
    filters: dict[str, Any] | None,
    *,
    last_sealed_at: Optional[datetime],
    now_utc: datetime,
    task_timezone: str,
) -> GmailZipUploadDecision:
    """Sin filas en BD: ``last_sealed_at`` es None."""
    f = filters or {}
    cadence_raw = str(f.get("vault_zip_cadence") or "weekly").strip().lower()
    if cadence_raw == "none":
        cadence = "none"
    elif cadence_raw in ("weekly", "monthly"):
        cadence = cadence_raw
    else:
        cadence = "weekly"

    anchor_dow = _filters_int(f, "vault_anchor_dow", 6)  # domingo por defecto
    anchor_dow = max(0, min(anchor_dow, 6))

    bootstrap_immediate = _filters_bool(f, "bootstrap_upload_immediate", True)

    tz = ZoneInfo((task_timezone or "UTC").strip() or "UTC")
    local_now = now_utc.astimezone(tz)
    today = local_now.date()
    dow = local_now.weekday()

    # --- Primera subida (sin sellado previo) ---
    if last_sealed_at is None:
        if bootstrap_immediate or dow == anchor_dow:
            sk = "bootstrap"
            return GmailZipUploadDecision(
                should_upload=True,
                period_start=today,
                period_end=today,
                seal_kind=sk,
                cadence_dir=seal_kind_to_zip_cadence_dir(sk),
                reason="bootstrap_first_seal",
            )
        return GmailZipUploadDecision(
            should_upload=False,
            period_start=today,
            period_end=today,
            seal_kind="bootstrap",
            cadence_dir="BOOTSTRAP",
            reason="bootstrap_waiting_anchor_or_flag",
        )

    last_local = last_sealed_at.astimezone(tz).date()

    # Evitar dos sellados el mismo día civil (TZ tarea).
    if last_local >= today:
        if cadence == "none":
            sk, cd = "bootstrap", seal_kind_to_zip_cadence_dir("bootstrap")
        elif cadence == "weekly":
            sk, cd = "weekly", "WEEKLY"
        else:
            sk, cd = "monthly", "MONTHLY"
        return GmailZipUploadDecision(
            should_upload=False,
            period_start=today,
            period_end=today,
            seal_kind=sk,
            cadence_dir=cd,
            reason="already_sealed_today",
        )

    if cadence == "none":
        return GmailZipUploadDecision(
            should_upload=False,
            period_start=today,
            period_end=today,
            seal_kind="bootstrap",
            cadence_dir="BOOTSTRAP",
            reason="vault_zip_cadence_none",
        )

    if cadence == "weekly":
        if dow != anchor_dow:
            return GmailZipUploadDecision(
                should_upload=False,
                period_start=last_local + timedelta(days=1),
                period_end=today,
                seal_kind="weekly",
                cadence_dir="WEEKLY",
                reason=f"weekly_wait_anchor_dow(want={anchor_dow}, today={dow})",
            )
        p0 = last_local + timedelta(days=1)
        return GmailZipUploadDecision(
            should_upload=True,
            period_start=p0,
            period_end=today,
            seal_kind="weekly",
            cadence_dir="WEEKLY",
            reason="weekly_anchor_day",
        )

    # monthly
    if dow != anchor_dow:
        return GmailZipUploadDecision(
            should_upload=False,
            period_start=last_local + timedelta(days=1),
            period_end=today,
            seal_kind="monthly",
            cadence_dir="MONTHLY",
            reason=f"monthly_wait_anchor_dow(want={anchor_dow}, today={dow})",
        )
    if (today.year, today.month) <= (last_local.year, last_local.month):
        return GmailZipUploadDecision(
            should_upload=False,
            period_start=last_local + timedelta(days=1),
            period_end=today,
            seal_kind="monthly",
            cadence_dir="MONTHLY",
            reason="monthly_already_sealed_this_month",
        )
    p0 = last_local + timedelta(days=1)
    return GmailZipUploadDecision(
        should_upload=True,
        period_start=p0,
        period_end=today,
        seal_kind="monthly",
        cadence_dir="MONTHLY",
        reason="monthly_anchor_new_month",
    )
