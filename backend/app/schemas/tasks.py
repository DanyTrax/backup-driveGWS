"""Schemas for BackupTask CRUD."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_serializer

from app.models.enums import BackupMode, BackupScope, ScheduleKind


def _dt_in_app_tz(v: datetime | None) -> datetime | None:
    if v is None:
        return None
    from datetime import timezone as dt_timezone

    from app.core.config import get_settings

    if v.tzinfo is None:
        v = v.replace(tzinfo=dt_timezone.utc)
    return v.astimezone(ZoneInfo(get_settings().tz))


class TaskCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=400)
    is_enabled: bool = True
    scope: BackupScope
    mode: BackupMode = BackupMode.INCREMENTAL
    schedule_kind: ScheduleKind = ScheduleKind.DAILY
    cron_expression: str | None = None
    run_at_hour: int | None = Field(default=None, ge=0, le=23)
    run_at_minute: int | None = Field(default=None, ge=0, le=59)
    timezone: str = "America/Bogota"
    retention_policy: dict[str, Any] = Field(default_factory=dict)
    filters: dict[str, Any] = Field(default_factory=dict)
    notify_channels: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = False
    checksum_enabled: bool = True
    max_parallel_accounts: int = Field(default=2, ge=1, le=32)
    account_ids: list[str] = []


class TaskUpdate(TaskCreate):
    pass


class TaskOut(BaseModel):
    id: str
    name: str
    description: str | None
    is_enabled: bool
    scope: str
    mode: str
    schedule_kind: str
    cron_expression: str | None
    run_at_hour: int | None
    run_at_minute: int | None
    timezone: str
    retention_policy: dict[str, Any]
    filters: dict[str, Any]
    notify_channels: dict[str, Any]
    dry_run: bool
    checksum_enabled: bool
    max_parallel_accounts: int
    account_ids: list[str]
    last_run_at: datetime | None
    last_status: str | None
    created_at: datetime

    @field_serializer("created_at", "last_run_at")
    def _task_times_app_tz(self, v: datetime | None) -> datetime | None:
        return _dt_in_app_tz(v)


class SkippedActiveBackupOut(BaseModel):
    account_id: str
    email: str | None = None
    kind: str  # gmail | drive
    active_log_id: str


class RunResultOut(BaseModel):
    queued: int
    celery_ids: list[str]
    batch_id: str
    skipped_due_to_active: list[SkippedActiveBackupOut] = Field(default_factory=list)


class RunEstimatePart(BaseModel):
    min_minutes: int | None
    max_minutes: int | None
    basis: str


class RunEstimateItem(BaseModel):
    email: str
    gmail: RunEstimatePart | None = None
    drive: RunEstimatePart | None = None


class RunEstimateOut(BaseModel):
    task_id: str
    scope: str
    mode: str
    items: list[RunEstimateItem]
    sum_minutes_min: int | None
    sum_minutes_max: int | None
    disclaimer: str


class BackupLogOut(BaseModel):
    id: str
    task_id: str
    account_id: str
    run_batch_id: str | None
    status: str
    scope: str
    mode: str
    started_at: datetime | None
    finished_at: datetime | None
    bytes_transferred: int
    files_count: int
    messages_count: int
    errors_count: int
    celery_task_id: str | None
    sha256_manifest_path: str | None
    destination_path: str | None
    error_summary: str | None
    detail_log_path: str | None = None
    gmail_maildir_ready_at: datetime | None = None
    gmail_vault_completed_at: datetime | None = None
    task_name: str | None = None
    account_email: str | None = None
    live_progress: dict[str, Any] | None = None

    @field_serializer(
        "started_at",
        "finished_at",
        "gmail_maildir_ready_at",
        "gmail_vault_completed_at",
    )
    def _log_times_app_tz(self, v: datetime | None) -> datetime | None:
        return _dt_in_app_tz(v)


class BackupLogBulkDeleteIn(BaseModel):
    log_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)


class BackupLogBulkDeleteOut(BaseModel):
    deleted: int
    skipped_running: list[str] = Field(default_factory=list)
    not_found: list[str] = Field(default_factory=list)
