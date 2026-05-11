"""audit_action: host_tmp_cleanup_gyb_zip"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016_audit_host_tmp_cleanup_gyb_zip"
down_revision = "0015_gmail_vault_state_tables"  # matches 0015 file revision id
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'host_tmp_cleanup_gyb_zip'"))


def downgrade() -> None:
    pass
