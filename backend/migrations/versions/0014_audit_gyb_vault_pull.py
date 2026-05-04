"""Auditoría: gyb_work_restored_from_vault.

Revision ID: 0014_audit_gyb_vault_pull
Revises: 0013_vault_drive_browser
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0014_audit_gyb_vault_pull"
down_revision: Union[str, None] = "0013_vault_drive_browser"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'gyb_work_restored_from_vault'")


def downgrade() -> None:
    pass
