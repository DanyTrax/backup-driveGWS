"""RBAC host Docker / stack deploy + audit actions.

Revision ID: 0011_host_ops_rbac_audit
Revises: 0010_operator_branding
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

revision: str = "0011_host_ops_rbac_audit"
down_revision: Union[str, None] = "0010_operator_branding"
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
    op.execute(sa.text("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'host_docker_prune'"))
    op.execute(sa.text("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'stack_deploy'"))

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
