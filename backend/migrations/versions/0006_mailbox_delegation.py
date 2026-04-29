"""Tabla de delegación Maildir + permisos mailbox.* en catálogo RBAC.

Revision ID: 0006_mailbox_delegation
Revises: 0005_password_assign
"""
from __future__ import annotations

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.permissions_catalog import (
    DEFAULT_ROLE_PERMISSIONS,
    PERMISSIONS,
    ROLE_DISPLAY,
)
from app.models.enums import UserRole

revision: str = "0006_mailbox_delegation"
down_revision: Union[str, None] = "0005_password_assign"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _upsert_role(bind, code: str, name: str, description: str) -> uuid.UUID:
    existing = bind.execute(
        sa.text("SELECT id FROM sys_roles WHERE code = :code"), {"code": code}
    ).fetchone()
    if existing:
        return existing[0]
    rid = uuid.uuid4()
    bind.execute(
        sa.text(
            "INSERT INTO sys_roles (id, code, name, description, is_system) "
            "VALUES (:id, :code, :name, :description, TRUE)"
        ),
        {"id": str(rid), "code": code, "name": name, "description": description},
    )
    return rid


def _upsert_permission(
    bind, code: str, module: str, action: str, description: str
) -> uuid.UUID:
    existing = bind.execute(
        sa.text("SELECT id FROM sys_permissions WHERE code = :code"), {"code": code}
    ).fetchone()
    if existing:
        return existing[0]
    pid = uuid.uuid4()
    bind.execute(
        sa.text(
            "INSERT INTO sys_permissions (id, code, module, action, description) "
            "VALUES (:id, :code, :module, :action, :description)"
        ),
        {
            "id": str(pid),
            "code": code,
            "module": module,
            "action": action,
            "description": description,
        },
    )
    return pid


def upgrade() -> None:
    op.create_table(
        "sys_user_mailbox_delegations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("sys_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("gw_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("granted_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["gw_account_id"],
            ["gw_accounts.id"],
            name="fk_sys_user_mailbox_delegations_gw_account_id_gw_accounts",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["granted_by_user_id"],
            ["sys_users.id"],
            name="fk_sys_user_mailbox_delegations_granted_by_user_id_sys_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["sys_user_id"],
            ["sys_users.id"],
            name="fk_sys_user_mailbox_delegations_sys_user_id_sys_users",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "sys_user_id",
            "gw_account_id",
            name="uq_mailbox_delegation_user_account",
        ),
    )
    op.create_index(
        "ix_sys_user_mailbox_delegations_gw_account_id",
        "sys_user_mailbox_delegations",
        ["gw_account_id"],
        unique=False,
    )
    op.create_index(
        "ix_sys_user_mailbox_delegations_sys_user_id",
        "sys_user_mailbox_delegations",
        ["sys_user_id"],
        unique=False,
    )

    bind = op.get_bind()
    role_ids: dict[str, uuid.UUID] = {}
    for role in UserRole:
        name, description = ROLE_DISPLAY[role]
        role_ids[role.value] = _upsert_role(bind, role.value, name, description)

    perm_ids: dict[str, uuid.UUID] = {}
    for p in PERMISSIONS:
        perm_ids[p.code] = _upsert_permission(bind, p.code, p.module, p.action, p.description)

    for role, allowed_codes in DEFAULT_ROLE_PERMISSIONS.items():
        role_id = role_ids[role.value]
        for code in allowed_codes:
            pid = perm_ids.get(code)
            if not pid:
                continue
            bind.execute(
                sa.text(
                    "INSERT INTO sys_role_permissions (role_id, permission_id) "
                    "VALUES (:role_id, :permission_id) "
                    "ON CONFLICT (role_id, permission_id) DO NOTHING"
                ),
                {"role_id": str(role_id), "permission_id": str(pid)},
            )


def downgrade() -> None:
    op.drop_index("ix_sys_user_mailbox_delegations_sys_user_id", table_name="sys_user_mailbox_delegations")
    op.drop_index("ix_sys_user_mailbox_delegations_gw_account_id", table_name="sys_user_mailbox_delegations")
    op.drop_table("sys_user_mailbox_delegations")
    # No eliminamos filas de sys_permissions: otras instalaciones podrían depender de ellas.
