"""Añade valor password_assign a webmail_token_purpose (landing de asignación de clave IMAP).

Revision ID: 0005_webmail_token_password_assign
Revises: 0004_backup_log_run_batch
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

revision: str = "0005_webmail_token_password_assign"
down_revision: Union[str, None] = "0004_backup_log_run_batch"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # no usar op.get_bind(): ya está en la transacción de env.py (begin_transaction) y
    # SQLAlchemy no deja fijar AUTOCOMMIT en esa conexión. Tampoco alterar conexión
    # "compartida" con Alembic async. Motor síncrono aparte, una sola sentencia.
    op_bind = op.get_bind()
    if op_bind.dialect.name != "postgresql":
        return
    from app.core.config import get_settings

    url = get_settings().database_url
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.connect() as c:
            c = c.execution_options(isolation_level="AUTOCOMMIT")
            c.execute(
                text(
                    "ALTER TYPE webmail_token_purpose ADD VALUE IF NOT EXISTS 'password_assign'"
                )
            )
    finally:
        engine.dispose()


def downgrade() -> None:
    # PostgreSQL no elimina valores de enum de forma portátil.
    pass
