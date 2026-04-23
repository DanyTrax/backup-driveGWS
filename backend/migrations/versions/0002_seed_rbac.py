"""seed RBAC catalog (roles + permissions + mapping)

Revision ID: 0002_seed_rbac
Revises: 0001_initial
Create Date: 2026-04-22 22:10:00

Idempotent data migration that populates sys_roles, sys_permissions and
sys_role_permissions from the canonical catalog in
``app.core.permissions_catalog``. Running it twice is a no-op.

The SuperAdmin user is NOT created here: use scripts/bootstrap_admin.py
interactively on the host so the operator picks the credentials.
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

revision: str = "0002_seed_rbac"
down_revision: Union[str, None] = "0001_initial"
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
    bind = op.get_bind()

    role_ids: dict[str, uuid.UUID] = {}
    for role in UserRole:
        name, description = ROLE_DISPLAY[role]
        role_ids[role.value] = _upsert_role(bind, role.value, name, description)

    perm_ids: dict[str, uuid.UUID] = {}
    for p in PERMISSIONS:
        perm_ids[p.code] = _upsert_permission(bind, p.code, p.module, p.action, p.description)

    # Role <-> permission wiring (idempotent via composite PK and NOT EXISTS)
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
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM sys_role_permissions"))
    bind.execute(sa.text("DELETE FROM sys_permissions"))
    bind.execute(sa.text("DELETE FROM sys_roles WHERE is_system = TRUE"))
