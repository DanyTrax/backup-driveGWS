"""Ensanchar ``alembic_version.version_num`` (Postgres: era varchar 32)."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017_alembic_version_widen"
down_revision = "0016_audit_gyb_zip_tmp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128)")
    )


def downgrade() -> None:
    op.execute(
        sa.text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(32)")
    )
