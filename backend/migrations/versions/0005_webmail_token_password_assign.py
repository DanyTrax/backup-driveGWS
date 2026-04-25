"""Añade valor password_assign a webmail_token_purpose (landing de asignación de clave IMAP).

Revision ID: 0005_webmail_token_password_assign
Revises: 0004_backup_log_run_batch
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0005_webmail_token_password_assign"
down_revision: Union[str, None] = "0004_backup_log_run_batch"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ADD VALUE a veces no puede ejecutarse en la transacción implícita de Alembic
    # (p. ej. en PostgreSQL, según el driver) y hace que falle el entrypoint antes
    # de levantar Uvicorn → 502 vía Nginx/Cloudflare. Usar conexión en AUTOCOMMIT.
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return
    ac = conn.execution_options(isolation_level="AUTOCOMMIT")
    ac.execute(
        text(
            "ALTER TYPE webmail_token_purpose ADD VALUE IF NOT EXISTS 'password_assign'"
        )
    )


def downgrade() -> None:
    # PostgreSQL no elimina valores de enum de forma portátil.
    pass
