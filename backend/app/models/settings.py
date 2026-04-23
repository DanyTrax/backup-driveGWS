"""Key-value system settings with optional encryption-at-rest."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.crypto import decrypt_str, encrypt_str
from app.models.base import Base, TimestampMixin, UUIDPKMixin


class SysSetting(UUIDPKMixin, TimestampMixin, Base):
    """One key-value pair.

    If ``is_secret`` is True the caller MUST go through :meth:`set_plaintext` /
    :meth:`get_plaintext` which wrap/unwrap with Fernet. The raw ``value`` then
    stores the ciphertext.
    """

    __tablename__ = "sys_settings"

    key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    value: Mapped[str | None] = mapped_column(Text)
    is_secret: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    category: Mapped[str] = mapped_column(String(32), nullable=False, server_default="general")
    description: Mapped[str | None] = mapped_column(String(400))

    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sys_users.id", ondelete="SET NULL"),
    )

    __table_args__ = (Index("ix_sys_settings_category", "category"),)

    # -- helpers -----------------------------------------------------------
    def set_plaintext(self, plaintext: str | None) -> None:
        if plaintext is None:
            self.value = None
            return
        self.value = encrypt_str(plaintext) if self.is_secret else plaintext

    def get_plaintext(self) -> str | None:
        if self.value is None:
            return None
        return decrypt_str(self.value) if self.is_secret else self.value

    def get_typed(self) -> Any:
        raw = self.get_plaintext()
        if raw is None:
            return None
        low = raw.strip().lower()
        if low in {"true", "false"}:
            return low == "true"
        try:
            return int(raw)
        except ValueError:
            pass
        return raw
