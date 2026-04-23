"""User, role, permission and session models."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Table,
    UniqueConstraint,
    Column,
)
from sqlalchemy.dialects.postgresql import INET, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import user_role_enum, user_status_enum

if TYPE_CHECKING:
    from app.models.notifications import SysUserNotificationPref


# ---------------------------------------------------------------------------
# Association table: role <-> permission  (many-to-many)
# ---------------------------------------------------------------------------
sys_role_permissions = Table(
    "sys_role_permissions",
    Base.metadata,
    Column("role_id", UUID(as_uuid=True), ForeignKey("sys_roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", UUID(as_uuid=True), ForeignKey("sys_permissions.id", ondelete="CASCADE"), primary_key=True),
)


# ---------------------------------------------------------------------------
class SysRole(UUIDPKMixin, TimestampMixin, Base):
    """Role = named bundle of permissions. Seeded with 3 defaults."""

    __tablename__ = "sys_roles"

    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    permissions: Mapped[list["SysPermission"]] = relationship(
        "SysPermission",
        secondary=sys_role_permissions,
        back_populates="roles",
        lazy="selectin",
    )
    users: Mapped[list["SysUser"]] = relationship(back_populates="role")


# ---------------------------------------------------------------------------
class SysPermission(UUIDPKMixin, TimestampMixin, Base):
    """Fine-grained permission. Format: <module>.<action> e.g. users.create."""

    __tablename__ = "sys_permissions"

    code: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    module: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))

    roles: Mapped[list["SysRole"]] = relationship(
        "SysRole",
        secondary=sys_role_permissions,
        back_populates="permissions",
    )

    __table_args__ = (
        UniqueConstraint("module", "action", name="uq_sys_permissions_module_action"),
        Index("ix_sys_permissions_module", "module"),
    )


# ---------------------------------------------------------------------------
class SysUser(UUIDPKMixin, TimestampMixin, Base):
    """Platform user (admin / operator / auditor)."""

    __tablename__ = "sys_users"

    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sys_roles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    role: Mapped["SysRole"] = relationship(back_populates="users", lazy="joined")

    status: Mapped[str] = mapped_column(
        user_status_enum,
        nullable=False,
        server_default="active",
    )

    # Legacy column for quick filtering without joining the roles table.
    role_code: Mapped[str] = mapped_column(
        user_role_enum,
        nullable=False,
        server_default="auditor",
    )

    # ---- MFA ----
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_secret_encrypted: Mapped[str | None] = mapped_column(String(512))
    mfa_backup_codes_encrypted: Mapped[str | None] = mapped_column(String(2048))
    mfa_enrolled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # ---- Login security / lockout ----
    failed_login_count: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="0"
    )
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_ip: Mapped[str | None] = mapped_column(INET)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # ---- Preferences (serialised JSON in sys_user_notification_prefs) ----
    preferred_locale: Mapped[str] = mapped_column(String(8), nullable=False, server_default="es")
    preferred_timezone: Mapped[str] = mapped_column(String(48), nullable=False, server_default="America/Bogota")

    sessions: Mapped[list["SysSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    notification_pref: Mapped["SysUserNotificationPref | None"] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )

    __table_args__ = (
        CheckConstraint("failed_login_count >= 0", name="failed_login_count_non_negative"),
        Index("ix_sys_users_status", "status"),
    )


# ---------------------------------------------------------------------------
class SysSession(UUIDPKMixin, TimestampMixin, Base):
    """JWT refresh-token companion row. Deleting it revokes the session."""

    __tablename__ = "sys_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sys_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user: Mapped["SysUser"] = relationship(back_populates="sessions")

    jti: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    refresh_token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(400))
    ip_address: Mapped[str | None] = mapped_column(INET)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_sys_sessions_user_revoked", "user_id", "revoked_at"),
    )
