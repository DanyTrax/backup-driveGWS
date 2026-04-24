"""Google Workspace accounts discovered via Admin SDK + sync history."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import (
    account_auth_method_enum,
    account_status_enum,
)

if TYPE_CHECKING:
    from app.models.tasks import BackupTask


class GwAccount(UUIDPKMixin, TimestampMixin, Base):
    """One row per Google Workspace user eligible for backup."""

    __tablename__ = "gw_accounts"

    # --- Identity (from Admin SDK Directory) ------------------------------
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    google_user_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    full_name: Mapped[str | None] = mapped_column(String(160))
    given_name: Mapped[str | None] = mapped_column(String(80))
    family_name: Mapped[str | None] = mapped_column(String(80))
    org_unit_path: Mapped[str | None] = mapped_column(String(255), index=True)
    is_workspace_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    workspace_status: Mapped[str] = mapped_column(
        account_status_enum, nullable=False, server_default="discovered"
    )

    # --- Opt-in flag ------------------------------------------------------
    is_backup_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", index=True
    )
    backup_enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    backup_enabled_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sys_users.id", ondelete="SET NULL")
    )
    exclusion_reason: Mapped[str | None] = mapped_column(String(255))
    discovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # --- Auth material used by rclone / gyb -------------------------------
    auth_method: Mapped[str] = mapped_column(
        account_auth_method_enum,
        nullable=False,
        server_default="service_account_dwd",
    )
    encrypted_refresh_token: Mapped[str | None] = mapped_column(Text)
    delegated_subject: Mapped[str | None] = mapped_column(String(255))

    # --- Webmail access (Dovecot virtual user) ----------------------------
    imap_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    imap_password_hash: Mapped[str | None] = mapped_column(String(255))
    imap_password_set_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    imap_last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    imap_last_login_ip: Mapped[str | None] = mapped_column(INET)
    imap_failed_attempts: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    imap_locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # --- Filesystem paths -------------------------------------------------
    maildir_path: Mapped[str | None] = mapped_column(String(500))
    # Si no es None, el admin vació la bandeja; UI muestra “sin bandeja” hasta próximo backup/provisión.
    maildir_user_cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    drive_vault_folder_id: Mapped[str | None] = mapped_column(String(128))

    # --- Sync stats -------------------------------------------------------
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_successful_backup_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_bytes_cache: Mapped[int | None] = mapped_column(Integer)
    total_messages_cache: Mapped[int | None] = mapped_column(Integer)

    # --- Metadata ---------------------------------------------------------
    tags_json: Mapped[list | None] = mapped_column(JSONB)

    backup_tasks: Mapped[list["BackupTask"]] = relationship(
        secondary="backup_task_accounts",
        back_populates="accounts",
    )

    __table_args__ = (
        Index("ix_gw_accounts_org_enabled", "org_unit_path", "is_backup_enabled"),
    )


class GwSyncLog(UUIDPKMixin, TimestampMixin, Base):
    """History of every Workspace directory sync run."""

    __tablename__ = "gw_sync_log"

    triggered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sys_users.id", ondelete="SET NULL"),
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    accounts_total: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    accounts_new: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    accounts_updated: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    accounts_suspended: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    accounts_deleted: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text)
    raw_diff_json: Mapped[dict | None] = mapped_column(JSONB)
