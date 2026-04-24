"""backup_logs.run_batch_id — agrupa jobs del mismo disparo (manual o programado).

Revision ID: 0004_backup_log_run_batch
Revises: 0003_account_maildir_cleared
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_backup_log_run_batch"
down_revision: Union[str, None] = "0003_account_maildir_cleared"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "backup_logs",
        sa.Column("run_batch_id", sa.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_backup_logs_run_batch_id", "backup_logs", ["run_batch_id"])


def downgrade() -> None:
    op.drop_index("ix_backup_logs_run_batch_id", table_name="backup_logs")
    op.drop_column("backup_logs", "run_batch_id")
