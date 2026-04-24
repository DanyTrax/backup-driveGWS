"""gw_accounts.maildir_user_cleared_at — bandeja vaciada manualmente hasta próximo backup.

Revision ID: 0003_account_maildir_cleared
Revises: 0002_seed_rbac
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_account_maildir_cleared"
down_revision: Union[str, None] = "0002_seed_rbac"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "gw_accounts",
        sa.Column("maildir_user_cleared_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("gw_accounts", "maildir_user_cleared_at")
