"""sys_users.role_code como VARCHAR; permisos roles.*; rol gyb_mailbox_only.

Revision ID: 0012_custom_roles
Revises: 0011_host_ops_rbac_audit
"""
from __future__ import annotations

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012_custom_roles"
down_revision: Union[str, None] = "0011_host_ops_rbac_audit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    op.execute(sa.text("ALTER TABLE sys_users ALTER COLUMN role_code DROP DEFAULT"))
    op.execute(
        sa.text(
            "ALTER TABLE sys_users ALTER COLUMN role_code "
            "TYPE VARCHAR(32) USING role_code::text"
        )
    )
    op.execute(sa.text("ALTER TABLE sys_users ALTER COLUMN role_code SET DEFAULT 'auditor'"))
    op.execute(sa.text("DROP TYPE IF EXISTS user_role"))

    for code, module, action, desc in (
        ("roles.view", "roles", "view", "Ver roles y los permisos asignados"),
        ("roles.manage", "roles", "manage", "Crear, editar y eliminar roles personalizados"),
    ):
        bind.execute(
            sa.text(
                """
                INSERT INTO sys_permissions (id, code, module, action, description)
                VALUES (:id, :code, :module, :action, :description)
                ON CONFLICT (code) DO NOTHING
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "code": code,
                "module": module,
                "action": action,
                "description": desc,
            },
        )

    def _perm_id(c: str):
        row = bind.execute(
            sa.text("SELECT id FROM sys_permissions WHERE code = :c"), {"c": c}
        ).fetchone()
        return row[0] if row else None

    def _role_id(c: str):
        row = bind.execute(
            sa.text("SELECT id FROM sys_roles WHERE code = :c"), {"c": c}
        ).fetchone()
        return row[0] if row else None

    for rc in ("super_admin", "operator"):
        rid = _role_id(rc)
        for p in (
            "roles.view",
            "roles.manage",
            "users.create",
            "users.edit",
            "users.reset_password",
        ):
            pid = _perm_id(p)
            if rid and pid:
                bind.execute(
                    sa.text(
                        """
                        INSERT INTO sys_role_permissions (role_id, permission_id)
                        VALUES (:rid, :pid)
                        ON CONFLICT (role_id, permission_id) DO NOTHING
                        """
                    ),
                    {"rid": str(rid), "pid": str(pid)},
                )

    gcode = "gyb_mailbox_only"
    row = bind.execute(
        sa.text("SELECT id FROM sys_roles WHERE code = :c"), {"c": gcode}
    ).fetchone()
    if row:
        gid = row[0]
    else:
        gid = uuid.uuid4()
        bind.execute(
            sa.text(
                """
                INSERT INTO sys_roles (id, code, name, description, is_system)
                VALUES (:id, :code, :name, :desc, FALSE)
                """
            ),
            {
                "id": str(gid),
                "code": gcode,
                "name": "Solo GYB / Maildir delegado",
                "desc": "Bandejas GYB (disco y Drive) y visor Maildir solo en cuentas delegadas por un administrador.",
            },
        )
    mid = _perm_id("mailbox.view_delegated")
    if mid:
        bind.execute(
            sa.text(
                """
                INSERT INTO sys_role_permissions (role_id, permission_id)
                VALUES (:rid, :pid)
                ON CONFLICT (role_id, permission_id) DO NOTHING
                """
            ),
            {"rid": str(gid), "pid": str(mid)},
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM sys_role_permissions WHERE role_id IN (SELECT id FROM sys_roles WHERE code = 'gyb_mailbox_only')"))
    bind.execute(sa.text("DELETE FROM sys_roles WHERE code = 'gyb_mailbox_only'"))
    bind.execute(
        sa.text(
            "DELETE FROM sys_role_permissions WHERE permission_id IN "
            "(SELECT id FROM sys_permissions WHERE code IN ('roles.view','roles.manage'))"
        )
    )
    bind.execute(
        sa.text("DELETE FROM sys_permissions WHERE code IN ('roles.view','roles.manage')")
    )

    op.execute(
        sa.text("CREATE TYPE user_role AS ENUM ('super_admin', 'operator', 'auditor')")
    )
    op.execute(sa.text("ALTER TABLE sys_users ALTER COLUMN role_code DROP DEFAULT"))
    op.execute(
        sa.text(
            "ALTER TABLE sys_users ALTER COLUMN role_code "
            "TYPE user_role USING role_code::user_role"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE sys_users ALTER COLUMN role_code SET DEFAULT 'auditor'::user_role"
        )
    )
