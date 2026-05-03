"""Visor bóveda Drive: permisos vault_drive.* y delegaciones por cuenta.

Revision ID: 0013_vault_drive_browser
Revises: 0012_custom_roles
"""
from __future__ import annotations

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013_vault_drive_browser"
down_revision: Union[str, None] = "0012_custom_roles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    op.create_table(
        "sys_user_vault_drive_delegations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("sys_user_id", sa.Uuid(), nullable=False),
        sa.Column("gw_account_id", sa.Uuid(), nullable=False),
        sa.Column("granted_by_user_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["granted_by_user_id"],
            ["sys_users.id"],
            name="fk_vault_drv_del_granted_by",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["gw_account_id"],
            ["gw_accounts.id"],
            name="fk_vault_drv_del_gw_account",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sys_user_id"],
            ["sys_users.id"],
            name="fk_vault_drv_del_sys_user",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sys_user_id",
            "gw_account_id",
            name="uq_vault_drive_delegation_user_account",
        ),
    )
    op.create_index(
        "ix_sys_user_vault_drive_delegations_sys_user_id",
        "sys_user_vault_drive_delegations",
        ["sys_user_id"],
    )
    op.create_index(
        "ix_sys_user_vault_drive_delegations_gw_account_id",
        "sys_user_vault_drive_delegations",
        ["gw_account_id"],
    )

    for code, module, action, desc in (
        (
            "vault_drive.view_all",
            "vault_drive",
            "view_all",
            "Explorar la bóveda de respaldo en Drive de cualquier cuenta (árbol y búsqueda)",
        ),
        (
            "vault_drive.view_delegated",
            "vault_drive",
            "view_delegated",
            "Explorar la bóveda solo en cuentas delegadas explícitamente",
        ),
        (
            "vault_drive.delegate",
            "vault_drive",
            "delegate",
            "Asignar o quitar cuentas para el visor de bóveda Drive (delegación)",
        ),
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

    role_perms: dict[str, tuple[str, ...]] = {
        "super_admin": (
            "vault_drive.view_all",
            "vault_drive.view_delegated",
            "vault_drive.delegate",
        ),
        "operator": ("vault_drive.view_all", "vault_drive.delegate"),
        "auditor": ("vault_drive.view_delegated",),
    }
    for rcode, plist in role_perms.items():
        rid = _role_id(rcode)
        if not rid:
            continue
        for p in plist:
            pid = _perm_id(p)
            if pid:
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


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM sys_user_vault_drive_delegations"))
    bind.execute(
        sa.text(
            "DELETE FROM sys_role_permissions WHERE permission_id IN "
            "(SELECT id FROM sys_permissions WHERE code LIKE 'vault_drive.%')"
        )
    )
    bind.execute(sa.text("DELETE FROM sys_permissions WHERE code LIKE 'vault_drive.%'"))
    op.drop_index(
        "ix_sys_user_vault_drive_delegations_gw_account_id",
        table_name="sys_user_vault_drive_delegations",
    )
    op.drop_index(
        "ix_sys_user_vault_drive_delegations_sys_user_id",
        table_name="sys_user_vault_drive_delegations",
    )
    op.drop_table("sys_user_vault_drive_delegations")
