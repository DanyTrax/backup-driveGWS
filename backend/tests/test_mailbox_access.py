"""Reglas puras de acceso al visor Maildir."""
from __future__ import annotations

import uuid

from app.core.mailbox_access import mailbox_readable_for_account


def test_mailbox_view_all_opens_any() -> None:
    aid = uuid.uuid4()
    other = uuid.uuid4()
    assert mailbox_readable_for_account(
        {"mailbox.view_all", "accounts.view"},
        account_id=aid,
        delegated_account_ids=frozenset({other}),
    )
    assert mailbox_readable_for_account(
        {"mailbox.view_all"},
        account_id=aid,
        delegated_account_ids=frozenset(),
    )


def test_mailbox_view_delegated_requires_row() -> None:
    aid = uuid.uuid4()
    assert mailbox_readable_for_account(
        {"mailbox.view_delegated"},
        account_id=aid,
        delegated_account_ids=frozenset({aid}),
    )
    assert not mailbox_readable_for_account(
        {"mailbox.view_delegated"},
        account_id=aid,
        delegated_account_ids=frozenset(),
    )


def test_no_mailbox_perm() -> None:
    aid = uuid.uuid4()
    assert not mailbox_readable_for_account(
        {"accounts.view"},
        account_id=aid,
        delegated_account_ids=frozenset({aid}),
    )
