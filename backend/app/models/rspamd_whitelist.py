"""Entradas de lista blanca Rspamd (panel → feeds HTTP)."""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin

if TYPE_CHECKING:
    from app.models.users import SysUser


class RspamdWhitelistEntry(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "rspamd_whitelist_entries"

    raw_input: Mapped[str] = mapped_column(String(320), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    value: Mapped[str] = mapped_column(String(255), nullable=False)

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sys_users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_by: Mapped[SysUser | None] = relationship("SysUser", foreign_keys=[created_by_user_id])

    __table_args__ = (
        UniqueConstraint("kind", "value", name="uq_rspamd_whitelist_entries_kind_value"),
        Index("ix_rspamd_whitelist_entries_value", "value"),
        Index("ix_rspamd_whitelist_entries_kind", "kind"),
    )
