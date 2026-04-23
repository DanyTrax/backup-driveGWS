"""Backup tasks (definitions) and backup logs (runs)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Table,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import (
    backup_mode_enum,
    backup_scope_enum,
    backup_status_enum,
    schedule_kind_enum,
)


# ---------------------------------------------------------------------------
# Many-to-many: backup_tasks <-> gw_accounts
# ---------------------------------------------------------------------------
backup_task_accounts = Table(
    "backup_task_accounts",
    Base.metadata,
    Column(
        "task_id",
        UUID(as_uuid=True),
        ForeignKey("backup_tasks.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "account_id",
        UUID(as_uuid=True),
        ForeignKey("gw_accounts.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class BackupTask(UUIDPKMixin, TimestampMixin, Base):
    """A reusable backup job definition (schedule + scope + accounts)."""

    __tablename__ = "backup_tasks"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(400))
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    scope: Mapped[str] = mapped_column(backup_scope_enum, nullable=False)
    mode: Mapped[str] = mapped_column(backup_mode_enum, nullable=False, server_default="incremental")

    schedule_kind: Mapped[str] = mapped_column(
        schedule_kind_enum, nullable=False, server_default="daily"
    )
    cron_expression: Mapped[str | None] = mapped_column(String(64))
    run_at_hour: Mapped[int | None] = mapped_column(SmallInteger)
    run_at_minute: Mapped[int | None] = mapped_column(SmallInteger)
    timezone: Mapped[str] = mapped_column(
        String(48), nullable=False, server_default="America/Bogota"
    )

    # Policy
    retention_policy_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    # Extra filters (drive folder whitelist, gmail labels, etc.)
    filters_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    notify_channels_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    checksum_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    # Concurrency cap per task
    max_parallel_accounts: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="2"
    )

    # Audit
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sys_users.id", ondelete="SET NULL")
    )
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str | None] = mapped_column(backup_status_enum)

    accounts: Mapped[list["GwAccount"]] = relationship(  # noqa: F821
        secondary=backup_task_accounts, back_populates="backup_tasks"
    )
    logs: Mapped[list["BackupLog"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_backup_tasks_is_enabled", "is_enabled"),)


class BackupLog(UUIDPKMixin, TimestampMixin, Base):
    """One row per actual run of a backup task (per account)."""

    __tablename__ = "backup_logs"

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("backup_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task: Mapped["BackupTask"] = relationship(back_populates="logs")

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gw_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    parent_log_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("backup_logs.id", ondelete="SET NULL"),
    )

    status: Mapped[str] = mapped_column(
        backup_status_enum, nullable=False, server_default="pending", index=True
    )
    scope: Mapped[str] = mapped_column(backup_scope_enum, nullable=False)
    mode: Mapped[str] = mapped_column(backup_mode_enum, nullable=False)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Process bookkeeping (rclone RC + pid tracking for control buttons)
    pid: Mapped[int | None] = mapped_column(Integer)
    rclone_rc_port: Mapped[int | None] = mapped_column(Integer)
    rclone_job_id: Mapped[str | None] = mapped_column(String(64))
    celery_task_id: Mapped[str | None] = mapped_column(String(64), index=True)

    # Result stats
    bytes_transferred: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    files_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    messages_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    errors_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    sha256_manifest_path: Mapped[str | None] = mapped_column(String(500))
    destination_path: Mapped[str | None] = mapped_column(String(500))
    error_summary: Mapped[str | None] = mapped_column(Text)
    detail_log_path: Mapped[str | None] = mapped_column(String(500))

    __table_args__ = (
        Index("ix_backup_logs_status_started", "status", "started_at"),
        Index("ix_backup_logs_account_started", "account_id", "started_at"),
    )
