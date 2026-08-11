"""Línea de sellado Gmail ZIP: heredar histórico desde BD (cualquier tarea) y/o ZIPs en Drive.

Permite borrar/crear/editar una tarea y retomar desde la última fecha ya respaldada
en la bóveda, sin re-descargar todo el correo.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.gmail_vault import GmailVaultAccountState
from app.services.gmail_vault_materialize_logic import VaultZipIndexEntry
from app.services.gmail_vault_zip_layout import gmail_vault_zip_object_rel_from_lsjson
from app.services.vault_layout import gmail_vault_packaging_mode

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SealLineage:
    last_sealed_at: datetime
    source: str  # task_db | account_db | vault_zip
    period_end: Optional[date] = None
    zip_rel_path: Optional[str] = None


def latest_zip_seal_from_entries(
    entries: list[VaultZipIndexEntry],
    *,
    account_id: uuid.UUID,
) -> Optional[SealLineage]:
    """Elige el ZIP con ``period_end`` más reciente."""
    if not entries:
        return None
    best = max(entries, key=lambda e: (e.period_end, e.period_start, e.rel_path))
    sealed_at = datetime.combine(best.period_end, time(23, 59, 59), tzinfo=UTC)
    rel = gmail_vault_zip_object_rel_from_lsjson(account_id, best.rel_path)
    return SealLineage(
        last_sealed_at=sealed_at,
        source="vault_zip",
        period_end=best.period_end,
        zip_rel_path=rel,
    )


def sealed_at_end_of_day(d: date, *, task_timezone: str) -> datetime:
    """Fin del día civil en TZ de la tarea → UTC (para ``last_sealed_at``)."""
    tz_name = (task_timezone or "UTC").strip() or "UTC"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")
    local = datetime.combine(d, time(23, 59, 59), tzinfo=tz)
    return local.astimezone(UTC)


def pick_best_lineage(*candidates: Optional[SealLineage]) -> Optional[SealLineage]:
    present = [c for c in candidates if c is not None]
    if not present:
        return None
    return max(present, key=lambda c: c.last_sealed_at)


async def max_sealed_across_account(
    db: AsyncSession,
    account_id: uuid.UUID,
) -> Optional[SealLineage]:
    """Mejor ``last_sealed_at`` entre todas las tareas de la cuenta."""
    stmt = (
        select(
            GmailVaultAccountState.last_sealed_at,
            GmailVaultAccountState.last_vault_zip_rel_path,
            GmailVaultAccountState.last_seal_kind,
        )
        .where(
            GmailVaultAccountState.account_id == account_id,
            GmailVaultAccountState.last_sealed_at.is_not(None),
        )
        .order_by(GmailVaultAccountState.last_sealed_at.desc())
        .limit(1)
    )
    row = (await db.execute(stmt)).one_or_none()
    if row is None or row[0] is None:
        return None
    sealed: datetime = row[0]
    if sealed.tzinfo is None:
        sealed = sealed.replace(tzinfo=UTC)
    return SealLineage(
        last_sealed_at=sealed,
        source="account_db",
        period_end=sealed.astimezone(UTC).date(),
        zip_rel_path=(row[1] or None),
    )


async def discover_seal_from_vault_zips(
    db: AsyncSession,
    *,
    account: Any,
) -> Optional[SealLineage]:
    """Lista ZIPs en Drive bajo ``1-GMAIL/zips/{account_id}/`` y toma el period_end máximo."""
    from app.services.gmail_vault_materialize_logic import GmailVaultMaterializeError
    from app.services.gmail_vault_materialize_service import rclone_lsjson_zips_for_account
    from app.services.rclone_service import build_rclone_vault_dest_only_config

    vid = (getattr(account, "drive_vault_folder_id", None) or "").strip()
    if not vid:
        return None
    account_id: uuid.UUID = account.id
    try:
        async with build_rclone_vault_dest_only_config(
            db, vault_folder_id=vid, account=account
        ) as cfg:
            # Timeout acotado: no bloquear el panel minutos sin telemetría.
            entries = await asyncio.wait_for(
                rclone_lsjson_zips_for_account(cfg, account_id),
                timeout=90.0,
            )
    except asyncio.TimeoutError:
        logger.warning(
            "seal_lineage vault lsjson timeout account=%s",
            account_id,
        )
        return None
    except GmailVaultMaterializeError as exc:
        logger.warning(
            "seal_lineage vault lsjson failed account=%s: %s",
            account_id,
            exc,
        )
        return None
    except Exception as exc:  # pragma: no cover
        logger.warning(
            "seal_lineage vault list failed account=%s: %s",
            account_id,
            exc,
            exc_info=True,
        )
        return None

    lineage = latest_zip_seal_from_entries(entries, account_id=account_id)
    if lineage is None:
        return None
    # Preferir fin de día en UTC ya puesto; period_end viene del nombre del ZIP.
    return SealLineage(
        last_sealed_at=sealed_at_end_of_day(
            lineage.period_end or lineage.last_sealed_at.date(),
            task_timezone="UTC",
        )
        if lineage.period_end
        else lineage.last_sealed_at,
        source="vault_zip",
        period_end=lineage.period_end,
        zip_rel_path=lineage.zip_rel_path,
    )


async def bind_seal_lineage_for_task(
    db: AsyncSession,
    *,
    account: Any,
    task_id: uuid.UUID,
    filters: dict[str, Any] | None,
    task_timezone: str,
    probe_vault: bool = True,
) -> Optional[SealLineage]:
    """Resuelve la mejor línea de sellado y la escribe en el estado de *esta* tarea si hace falta.

    Fuentes (se elige la más reciente):
    - Estado de esta tarea
    - Máximo sellado de otras tareas de la misma cuenta
    - ZIPs ya existentes en la bóveda (Drive)
    """
    from app.services.gmail_vault_zip_service import (
        ensure_gmail_vault_account_state,
        load_gmail_vault_account_state,
    )

    packaging = gmail_vault_packaging_mode(filters)
    task_row = await load_gmail_vault_account_state(db, account_id=account.id, task_id=task_id)
    task_lineage: Optional[SealLineage] = None
    if task_row is not None and task_row.last_sealed_at is not None:
        sealed = task_row.last_sealed_at
        if sealed.tzinfo is None:
            sealed = sealed.replace(tzinfo=UTC)
        task_lineage = SealLineage(
            last_sealed_at=sealed,
            source="task_db",
            period_end=sealed.astimezone(UTC).date(),
            zip_rel_path=task_row.last_vault_zip_rel_path,
        )

    account_lineage = await max_sealed_across_account(db, account.id)

    vault_lineage: Optional[SealLineage] = None
    if probe_vault:
        vault_lineage = await discover_seal_from_vault_zips(db, account=account)
        if vault_lineage is not None and vault_lineage.period_end is not None:
            # Re-expresar fin de periodo en TZ de la tarea
            vault_lineage = SealLineage(
                last_sealed_at=sealed_at_end_of_day(
                    vault_lineage.period_end, task_timezone=task_timezone
                ),
                source="vault_zip",
                period_end=vault_lineage.period_end,
                zip_rel_path=vault_lineage.zip_rel_path,
            )

    best = pick_best_lineage(task_lineage, account_lineage, vault_lineage)
    if best is None:
        return None

    st = await ensure_gmail_vault_account_state(
        db,
        account_id=account.id,
        task_id=task_id,
        packaging_mode=packaging,
    )
    current = st.last_sealed_at
    if current is not None and current.tzinfo is None:
        current = current.replace(tzinfo=UTC)

    # Solo heredar / actualizar si esta tarea no tiene sellado o el descubierto es más nuevo.
    if current is None or best.last_sealed_at > current:
        st.last_sealed_at = best.last_sealed_at
        if best.source != "task_db":
            st.last_seal_kind = st.last_seal_kind or "manual"
        if best.zip_rel_path:
            st.last_vault_zip_rel_path = best.zip_rel_path
        prev = dict(st.watermark_json or {})
        prev["seal_lineage_source"] = best.source
        if best.period_end is not None:
            prev["inherited_period_end"] = best.period_end.isoformat()
        if best.zip_rel_path:
            prev["inherited_zip_rel"] = best.zip_rel_path
        st.watermark_json = prev
        await db.flush()

    return best
