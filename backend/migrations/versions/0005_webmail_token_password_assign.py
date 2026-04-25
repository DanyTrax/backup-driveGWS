"""Añade valor password_assign a webmail_token_purpose (landing de asignación de clave IMAP).

Revision ID: 0005_webmail_token_password_assign
Revises: 0004_backup_log_run_batch
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0005_webmail_token_password_assign"
down_revision: Union[str, None] = "0004_backup_log_run_batch"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE webmail_token_purpose ADD VALUE IF NOT EXISTS 'password_assign'")


def downgrade() -> None:
    # PostgreSQL no elimina valores de enum de forma portátil.
    pass
