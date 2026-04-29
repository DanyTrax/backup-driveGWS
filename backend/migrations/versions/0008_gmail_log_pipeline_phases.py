"""Gmail backup phases on backup_logs (Maildir ready vs vault pushed)."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_gmail_log_pipeline_phases"
down_revision = "0007_mail_data_purge_rbac"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "backup_logs",
        sa.Column("gmail_maildir_ready_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "backup_logs",
        sa.Column("gmail_vault_completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("backup_logs", "gmail_vault_completed_at")
    op.drop_column("backup_logs", "gmail_maildir_ready_at")
