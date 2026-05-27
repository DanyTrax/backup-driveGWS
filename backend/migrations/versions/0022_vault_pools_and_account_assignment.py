"""Pools de bóveda y asignación por cuenta (default | pool | dedicated)."""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022_vault_pools_and_account_assignment"
down_revision: Union[str, None] = "0021_rspamd_whitelist_include_subdomains"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vault_pools",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("shared_drive_id", sa.String(128), nullable=False),
        sa.Column("root_folder_id", sa.String(128), nullable=False),
        sa.Column("description", sa.Text()),
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
        sa.UniqueConstraint("shared_drive_id", name="uq_vault_pools_shared_drive_id"),
        sa.UniqueConstraint("name", name="uq_vault_pools_name"),
    )
    op.add_column(
        "gw_accounts",
        sa.Column("vault_mode", sa.String(16), nullable=False, server_default="default"),
    )
    op.add_column(
        "gw_accounts",
        sa.Column("vault_pool_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "gw_accounts",
        sa.Column("dedicated_shared_drive_id", sa.String(128), nullable=True),
    )
    op.create_foreign_key(
        "fk_gw_accounts_vault_pool_id_vault_pools",
        "gw_accounts",
        "vault_pools",
        ["vault_pool_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_gw_accounts_vault_pool_id", "gw_accounts", ["vault_pool_id"])


def downgrade() -> None:
    op.drop_index("ix_gw_accounts_vault_pool_id", table_name="gw_accounts")
    op.drop_constraint("fk_gw_accounts_vault_pool_id_vault_pools", "gw_accounts", type_="foreignkey")
    op.drop_column("gw_accounts", "dedicated_shared_drive_id")
    op.drop_column("gw_accounts", "vault_pool_id")
    op.drop_column("gw_accounts", "vault_mode")
    op.drop_table("vault_pools")
