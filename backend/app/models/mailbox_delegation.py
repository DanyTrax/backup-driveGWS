"""Delegación de lectura Maildir por usuario de plataforma."""
from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class SysUserMailboxDelegation(UUIDPKMixin, TimestampMixin, Base):
    """Permite leer el visor Maildir de una cuenta concreta (sin mailbox.view_all)."""

    __tablename__ = "sys_user_mailbox_delegations"

    sys_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sys_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    gw_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gw_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    granted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sys_users.id", ondelete="SET NULL"),
    )

    __table_args__ = (
        UniqueConstraint(
            "sys_user_id",
            "gw_account_id",
            name="uq_mailbox_delegation_user_account",
        ),
    )
