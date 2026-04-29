"""Audit backup_log_deleted + permiso logs.delete (export PDF en API).

Revision ID: 0009_backup_log_del_rbac  (<=32 chars para alembic_version VARCHAR(32))
Revises: 0008_gmail_log_pipeline_phases
"""
from __future__ import annotations

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.core.permissions_catalog import (
    DEFAULT_ROLE_PERMISSIONS,
    PERMISSIONS,
    ROLE_DISPLAY,
)
from app.models.enums import UserRole

revision: str = "0009_backup_log_del_rbac"
down_revision: Union[str, None] = "0008_gmail_log_pipeline_phases"
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
        bind.execute(
            sa.text(
                "UPDATE sys_permissions SET module = :module, action = :action, "
                "description = :description WHERE code = :code"
            ),
            {
                "code": code,
                "module": module,
                "action": action,
                "description": description,
            },
        )
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
    # ALTER TYPE … ADD VALUE no debe quedar en la misma transacción que el resto en algunas versiones de PostgreSQL.
    with op.get_context().autocommit_block():
        op.execute(
            sa.text(
                "ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'backup_log_deleted'"
            )
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
    pass
