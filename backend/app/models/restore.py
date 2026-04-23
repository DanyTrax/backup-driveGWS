"""Restore jobs (Drive files and Gmail messages)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import restore_scope_enum, restore_status_enum


class RestoreJob(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "restore_jobs"

    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sys_users.id", ondelete="SET NULL"), index=True
    )
    target_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gw_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_backup_log_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("backup_logs.id", ondelete="SET NULL"),
    )

    scope: Mapped[str] = mapped_column(restore_scope_enum, nullable=False)
    status: Mapped[str] = mapped_column(
        restore_status_enum, nullable=False, server_default="pending", index=True
    )

    # What to restore (depends on scope; interpreted by the worker)
    selection_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    # Where to restore
    destination_kind: Mapped[str] = mapped_column(String(32), nullable=False, server_default="original")
    destination_details_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )

    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    notify_client: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    preserve_original_dates: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    apply_restored_label: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    celery_task_id: Mapped[str | None] = mapped_column(String(64))

    items_total: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    items_restored: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    items_failed: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    bytes_restored: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")

    error_summary: Mapped[str | None] = mapped_column(Text)
    detail_log_path: Mapped[str | None] = mapped_column(String(500))

    __table_args__ = (
        Index("ix_restore_jobs_status_started", "status", "started_at"),
    )
