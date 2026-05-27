"""Unidades compartidas adicionales (pools) para repartir cuentas fuera del vault por defecto."""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin

if TYPE_CHECKING:
    from app.models.accounts import GwAccount


class VaultPool(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "vault_pools"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    shared_drive_id: Mapped[str] = mapped_column(String(128), nullable=False)
    root_folder_id: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    accounts: Mapped[list["GwAccount"]] = relationship(
        "GwAccount",
        back_populates="vault_pool",
        foreign_keys="GwAccount.vault_pool_id",
    )

    __table_args__ = (
        UniqueConstraint("shared_drive_id", name="uq_vault_pools_shared_drive_id"),
        UniqueConstraint("name", name="uq_vault_pools_name"),
    )
