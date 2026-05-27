from __future__ import annotations

from app.models.rspamd_whitelist import RspamdWhitelistEntry
from app.services.rspamd_whitelist_store import row_to_normalized_feed_entries


def test_row_to_feed_entries_domain_without_subdomains() -> None:
    row = RspamdWhitelistEntry(raw_input="cliente.com", kind="domain", value="cliente.com")
    row.include_subdomains = False
    out = row_to_normalized_feed_entries(row)
    assert [e.value for e in out] == ["cliente.com"]


def test_row_to_feed_entries_domain_with_subdomains() -> None:
    row = RspamdWhitelistEntry(raw_input="cliente.com", kind="domain", value="cliente.com")
    row.include_subdomains = True
    out = row_to_normalized_feed_entries(row)
    assert [e.value for e in out] == ["cliente.com", ".cliente.com"]


def test_row_to_feed_entries_email_ignores_subdomains_flag() -> None:
    row = RspamdWhitelistEntry(
        raw_input="ventas@cliente.com",
        kind="email",
        value="ventas@cliente.com",
    )
    row.include_subdomains = True
    out = row_to_normalized_feed_entries(row)
    assert [e.value for e in out] == ["ventas@cliente.com"]
