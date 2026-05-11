"""gw_accounts.total_bytes_cache INTEGER -> BIGINT (buzones > ~2 GB)."""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0019_gw_accounts_total_bytes_bigint"
down_revision: Union[str, None] = "0018_restore_job_delete_rbac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE gw_accounts ALTER COLUMN total_bytes_cache "
        "TYPE BIGINT USING total_bytes_cache::bigint"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE gw_accounts ALTER COLUMN total_bytes_cache "
        "TYPE INTEGER USING LEAST(total_bytes_cache, 2147483647)::integer"
    )
