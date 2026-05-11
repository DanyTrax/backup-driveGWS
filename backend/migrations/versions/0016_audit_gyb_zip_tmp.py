"""audit_action: host_tmp_cleanup_gyb_zip (id corto: alembic_version es varchar 32)."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# Máx. 32 caracteres — ``0016_audit_host_tmp_cleanup_gyb_zip`` era demasiado largo.
revision = "0016_audit_gyb_zip_tmp"
down_revision = "0015_gmail_vault_state_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'host_tmp_cleanup_gyb_zip'"))


def downgrade() -> None:
    pass
