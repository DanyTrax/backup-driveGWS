"""Tabla rspamd_whitelist_entries + permisos rspamd_whitelist.view/edit."""
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

revision: str = "0020_rspamd_whitelist_rbac"
down_revision: Union[str, None] = "0019_gw_accounts_total_bytes_bigint"
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
    op.create_table(
        "rspamd_whitelist_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("raw_input", sa.String(320), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("value", sa.String(255), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["sys_users.id"],
            ondelete="SET NULL",
            name="fk_rspamd_whitelist_entries_created_by_user_id_sys_users",
        ),
        sa.UniqueConstraint("kind", "value", name="uq_rspamd_whitelist_entries_kind_value"),
    )
    op.create_index(
        "ix_rspamd_whitelist_entries_value",
        "rspamd_whitelist_entries",
        ["value"],
    )
    op.create_index(
        "ix_rspamd_whitelist_entries_kind",
        "rspamd_whitelist_entries",
        ["kind"],
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
    op.drop_index("ix_rspamd_whitelist_entries_kind", table_name="rspamd_whitelist_entries")
    op.drop_index("ix_rspamd_whitelist_entries_value", table_name="rspamd_whitelist_entries")
    op.drop_table("rspamd_whitelist_entries")
