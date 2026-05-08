"""gmail_vault_account_state y gmail_vault_materialization (plan ZIP vault Fase 1).

Revision ID: 0015_gmail_vault_state_tables
Revises: 0014_audit_gyb_vault_pull
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_gmail_vault_state_tables"
down_revision: Union[str, None] = "0014_audit_gyb_vault_pull"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gmail_vault_account_state",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gw_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("backup_tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("packaging_mode", sa.String(32), nullable=False, server_default="legacy_eml"),
        sa.Column("last_sealed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seal_kind", sa.String(32), nullable=True),
        sa.Column("last_vault_zip_rel_path", sa.String(500), nullable=True),
        sa.Column(
            "watermark_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "account_id",
            "task_id",
            name="uq_gmail_vault_account_state_account_task",
        ),
    )
    op.create_index(
        "ix_gmail_vault_account_state_account",
        "gmail_vault_account_state",
        ["account_id"],
    )
    op.create_index(
        "ix_gmail_vault_account_state_task",
        "gmail_vault_account_state",
        ["task_id"],
    )

    op.create_table(
        "gmail_vault_materialization",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gw_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("backup_tasks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sys_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("requested_mode", sa.String(32), nullable=False),
        sa.Column("date_from", sa.Date(), nullable=True),
        sa.Column("date_to", sa.Date(), nullable=True),
        sa.Column("ttl_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("path_local", sa.String(500), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column(
            "progress_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_gmail_vault_materialization_account",
        "gmail_vault_materialization",
        ["account_id"],
    )
    op.create_index(
        "ix_gmail_vault_materialization_status",
        "gmail_vault_materialization",
        ["status"],
    )
    op.create_index(
        "ix_gmail_vault_materialization_ttl",
        "gmail_vault_materialization",
        ["ttl_expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_gmail_vault_materialization_ttl", table_name="gmail_vault_materialization")
    op.drop_index("ix_gmail_vault_materialization_status", table_name="gmail_vault_materialization")
    op.drop_index("ix_gmail_vault_materialization_account", table_name="gmail_vault_materialization")
    op.drop_table("gmail_vault_materialization")

    op.drop_index("ix_gmail_vault_account_state_task", table_name="gmail_vault_account_state")
    op.drop_index("ix_gmail_vault_account_state_account", table_name="gmail_vault_account_state")
    op.drop_table("gmail_vault_account_state")
