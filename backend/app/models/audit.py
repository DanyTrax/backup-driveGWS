"""Append-only audit log."""
from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import audit_action_enum


class SysAudit(UUIDPKMixin, TimestampMixin, Base):
    """Every sensitive action taken by a user or by the system itself.

    Rows are INSERT-only by convention; application code must never UPDATE or
    DELETE. A Postgres trigger can enforce this in Fase 2 if desired.
    """

    __tablename__ = "sys_audit"

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sys_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    actor_label: Mapped[str | None] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(audit_action_enum, nullable=False, index=True)
    target_table: Mapped[str | None] = mapped_column(String(64), index=True)
    target_id: Mapped[str | None] = mapped_column(String(128), index=True)
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(String(400))
    success: Mapped[bool] = mapped_column(nullable=False, server_default="true")
    message: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)

    __table_args__ = (
        Index("ix_sys_audit_created_at_desc", "created_at"),
        Index("ix_sys_audit_actor_action", "actor_user_id", "action"),
    )
