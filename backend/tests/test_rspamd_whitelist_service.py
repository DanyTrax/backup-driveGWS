"""Tests normalización mapas Rspamd."""
from __future__ import annotations

import pytest

from app.services.rspamd_whitelist_service import (
    WhitelistEntryKind,
    WhitelistNormalizeError,
    normalize_whitelist_input,
    parse_env_entry_lines,
    render_rspamd_map,
)


def test_domain_variants() -> None:
    for raw in ("Cliente.COM", "@cliente.com", "*@cliente.com"):
        ent = normalize_whitelist_input(raw)
        assert ent.kind == WhitelistEntryKind.domain
        assert ent.value == "cliente.com"


def test_email() -> None:
    ent = normalize_whitelist_input("Ventas@Proveedor.COM")
    assert ent.kind == WhitelistEntryKind.email
    assert ent.value == "ventas@proveedor.com"


def test_env_parse() -> None:
    blob = "a.com, @b.com\nuser@c.com"
    entries = parse_env_entry_lines(blob)
    domains = [e.value for e in entries if e.kind == WhitelistEntryKind.domain]
    emails = [e.value for e in entries if e.kind == WhitelistEntryKind.email]
    assert "a.com" in domains
    assert "b.com" in domains
    assert "user@c.com" in emails


def test_render_domain_map() -> None:
    entries = parse_env_entry_lines("solo.com")
    text = render_rspamd_map(entries, kind=WhitelistEntryKind.domain, title="t")
    assert "solo.com" in text
    assert "@" not in text.splitlines()[-2]


def test_invalid() -> None:
    with pytest.raises(WhitelistNormalizeError):
        normalize_whitelist_input("not a domain")
