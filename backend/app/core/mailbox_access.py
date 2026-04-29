"""Reglas de acceso al visor Maildir (coexisten con RBAC en base de datos)."""
from __future__ import annotations

import uuid


def mailbox_readable_for_account(
    permissions: set[str],
    *,
    account_id: uuid.UUID,
    delegated_account_ids: frozenset[uuid.UUID],
) -> bool:
    if "mailbox.view_all" in permissions:
        return True
    if "mailbox.view_delegated" in permissions and account_id in delegated_account_ids:
        return True
    return False
