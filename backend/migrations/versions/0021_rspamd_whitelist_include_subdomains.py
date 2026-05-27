"""Agrega flag include_subdomains en whitelist Rspamd."""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0021_rspamd_whitelist_include_subdomains"
down_revision: Union[str, None] = "0020_rspamd_whitelist_rbac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "rspamd_whitelist_entries",
        sa.Column("include_subdomains", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("rspamd_whitelist_entries", "include_subdomains")
