"""In-app notifications and per-user notification preferences."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import notification_severity_enum


class Notification(UUIDPKMixin, TimestampMixin, Base):
    """Row shown in the in-app bell; may be fanned out to external channels."""

    __tablename__ = "notifications"

    recipient_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sys_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(
        notification_severity_enum,
        nullable=False,
        server_default="info",
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    action_url: Mapped[str | None] = mapped_column(String(500))
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)

    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    delivered_channels_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )

    __table_args__ = (
        Index("ix_notifications_recipient_created", "recipient_user_id", "created_at"),
        Index("ix_notifications_recipient_unread", "recipient_user_id", "read_at"),
    )


class SysUserNotificationPref(UUIDPKMixin, TimestampMixin, Base):
    """One row per user with their channel preferences (JSON matrix)."""

    __tablename__ = "sys_user_notification_prefs"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sys_users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    user = relationship("SysUser", back_populates="notification_pref")

    # {
    #   "backup.failed":   ["in_app","toast","telegram","gmail"],
    #   "backup.success":  ["in_app"],
    #   "account.new":     ["in_app","modal"],
    #   ...
    # }
    channels_matrix_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )

    # Do-not-disturb windows in user tz, e.g. [{"from":"22:00","to":"06:00"}]
    quiet_hours_json: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    digest_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    digest_frequency: Mapped[str] = mapped_column(String(16), nullable=False, server_default="daily")

    telegram_chat_id: Mapped[str | None] = mapped_column(String(64))
    discord_webhook_url: Mapped[str | None] = mapped_column(String(400))
    gmail_recipient: Mapped[str | None] = mapped_column(String(255))
