"""Estado vault Gmail por cuenta/tarea y sesiones de materialización desde Drive (Fase 1).

La lógica de negocio (ZIP, GYB, manifiestos) se implementa en fases posteriores;
aquí solo persistimos el contrato de datos acordado en docs/planning/gmail-vault-zip-fase0-spec.md.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin

if TYPE_CHECKING:
    from app.models.accounts import GwAccount
    from app.models.tasks import BackupTask
    from app.models.users import SysUser


class GmailVaultAccountState(UUIDPKMixin, TimestampMixin, Base):
    """Último sellado vault + watermark por par (cuenta, tarea Gmail)."""

    __tablename__ = "gmail_vault_account_state"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "task_id",
            name="uq_gmail_vault_account_state_account_task",
        ),
        Index("ix_gmail_vault_account_state_account", "account_id"),
        Index("ix_gmail_vault_account_state_task", "task_id"),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gw_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("backup_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )

    #: legacy_eml | zip_only | mixed — espejo del filtro de tarea o último modo aplicado
    packaging_mode: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="legacy_eml"
    )

    #: Fin del periodo resguardado en vault (sellado lógico).
    last_sealed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    #: bootstrap | weekly | monthly | manual — último tipo de sellado
    last_seal_kind: Mapped[Optional[str]] = mapped_column(String(32))

    #: Ruta relativa bajo el remoto vault (ej. zips/{account_id}/…)
    last_vault_zip_rel_path: Mapped[Optional[str]] = mapped_column(String(500))

    #: Cursor Gmail / GYB / historyId según evolución del pipeline
    watermark_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )

    account: Mapped["GwAccount"] = relationship(  # noqa: F821
        "GwAccount",
        lazy="selectin",
        foreign_keys=[account_id],
    )
    task: Mapped["BackupTask"] = relationship(  # noqa: F821
        "BackupTask",
        lazy="selectin",
        foreign_keys=[task_id],
    )


class GmailVaultMaterialization(UUIDPKMixin, TimestampMixin, Base):
    """Sesión: bajar ZIP(s) del vault al servidor y unificar para el visor (Fase 5+)."""

    __tablename__ = "gmail_vault_materialization"
    __table_args__ = (
        Index("ix_gmail_vault_materialization_account", "account_id"),
        Index("ix_gmail_vault_materialization_status", "status"),
        Index("ix_gmail_vault_materialization_ttl", "ttl_expires_at"),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gw_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("backup_tasks.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sys_users.id", ondelete="SET NULL"),
        nullable=True,
    )

    #: single_day | date_range | month | all
    requested_mode: Mapped[str] = mapped_column(String(32), nullable=False)

    date_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    date_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    ttl_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    path_local: Mapped[str] = mapped_column(String(500), nullable=False)

    #: pending | downloading | extracting | ready | promoted | failed | expired | cancelled
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending")

    progress_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    error_summary: Mapped[Optional[str]] = mapped_column(Text)

    account: Mapped["GwAccount"] = relationship(  # noqa: F821
        "GwAccount",
        lazy="selectin",
        foreign_keys=[account_id],
    )
    task: Mapped[Optional["BackupTask"]] = relationship(  # noqa: F821
        "BackupTask",
        lazy="selectin",
        foreign_keys=[task_id],
    )
    created_by: Mapped[Optional["SysUser"]] = relationship(  # noqa: F821
        "SysUser",
        lazy="selectin",
        foreign_keys=[created_by_user_id],
    )
