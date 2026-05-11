"""API schemas: materialización vault ZIP Gmail (Fase 5)."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal, Optional, TYPE_CHECKING
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_serializer

if TYPE_CHECKING:
    from app.models.gmail_vault import GmailVaultMaterialization

ModeLiteral = Literal["single_day", "date_range", "month", "all"]


def _dt_in_app_tz(v: datetime | None) -> datetime | None:
    if v is None:
        return None
    from datetime import timezone as dt_timezone

    from app.core.config import get_settings

    if v.tzinfo is None:
        v = v.replace(tzinfo=dt_timezone.utc)
    return v.astimezone(ZoneInfo(get_settings().tz))


class GmailVaultMaterializeCreateIn(BaseModel):
    account_id: uuid.UUID
    task_id: Optional[uuid.UUID] = None
    mode: ModeLiteral
    anchor_date: Optional[date] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    calendar_month: Optional[str] = Field(
        default=None,
        max_length=7,
        description="Solo modo month: YYYY-MM",
    )
    ttl_days: Optional[int] = Field(
        default=None,
        ge=1,
        description="Días hasta expiración en disco; por defecto y tope máximo vienen de settings",
    )


class GmailVaultMaterializeOut(BaseModel):
    id: str
    account_id: str
    account_email: Optional[str] = None
    task_id: Optional[str] = None
    requested_mode: str
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    ttl_expires_at: datetime
    path_local: str
    status: str
    progress_json: dict[str, Any]
    error_summary: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    live_progress: Optional[dict[str, Any]] = None

    @field_serializer("created_at", "updated_at", "ttl_expires_at")
    def _times_app(self, v: datetime) -> datetime:
        return _dt_in_app_tz(v) or v


class GmailVaultMaterializeListItem(BaseModel):
    """Fila de historial (página de logs): sesión de materialización vault ZIP → disco."""

    id: str
    account_id: str
    account_email: Optional[str] = None
    task_id: Optional[str] = None
    task_name: Optional[str] = None
    requested_mode: str
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    status: str
    created_at: datetime
    updated_at: datetime
    ttl_expires_at: datetime
    error_summary: Optional[str] = None
    progress_json: dict[str, Any] = Field(default_factory=dict)

    @field_serializer("created_at", "updated_at", "ttl_expires_at")
    def _times_list_times(self, v: datetime) -> datetime:
        return _dt_in_app_tz(v) or v


def materialization_to_out(row: "GmailVaultMaterialization") -> GmailVaultMaterializeOut:
    from app.models.gmail_vault import GmailVaultMaterialization as _GVM

    assert isinstance(row, _GVM)
    return GmailVaultMaterializeOut(
        id=str(row.id),
        account_id=str(row.account_id),
        account_email=None,
        task_id=str(row.task_id) if row.task_id else None,
        requested_mode=row.requested_mode,
        date_from=row.date_from,
        date_to=row.date_to,
        ttl_expires_at=row.ttl_expires_at,
        path_local=row.path_local,
        status=row.status,
        progress_json=dict(row.progress_json or {}),
        error_summary=row.error_summary,
        created_at=row.created_at,
        updated_at=row.updated_at,
        live_progress=None,
    )
