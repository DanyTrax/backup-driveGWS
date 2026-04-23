"""Schemas for restore jobs."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import RestoreScope


class RestoreCreate(BaseModel):
    target_account_id: str
    scope: RestoreScope
    selection: dict[str, Any] = Field(default_factory=dict)
    destination_kind: str = "original"
    destination_details: dict[str, Any] = Field(default_factory=dict)
    source_backup_log_id: str | None = None
    dry_run: bool = False
    notify_client: bool = False
    preserve_original_dates: bool = True
    apply_restored_label: bool = True


class RestoreOut(BaseModel):
    id: str
    target_account_id: str
    scope: str
    status: str
    dry_run: bool
    items_total: int
    items_restored: int
    items_failed: int
    bytes_restored: int
    started_at: datetime | None
    finished_at: datetime | None
    error_summary: str | None
    created_at: datetime
