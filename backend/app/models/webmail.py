"""Webmail access tokens (magic links / SSO)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import INET, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import webmail_token_purpose_enum


class WebmailAccessToken(UUIDPKMixin, TimestampMixin, Base):
    """Hashed short-lived token consumed once.

    The plaintext token is emitted only once (inside the magic-link URL that
    the platform sends to the client). We store only its sha-256 hex digest so
    a database leak cannot grant account access.
    """

    __tablename__ = "webmail_access_tokens"

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gw_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    purpose: Mapped[str] = mapped_column(webmail_token_purpose_enum, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    issued_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sys_users.id", ondelete="SET NULL")
    )
    consumer_ip: Mapped[str | None] = mapped_column(INET)
    consumer_user_agent: Mapped[str | None] = mapped_column(String(400))

    __table_args__ = (
        Index("ix_webmail_tokens_account_purpose", "account_id", "purpose"),
    )
