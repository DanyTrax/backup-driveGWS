"""Placeholder tests — keep the suite green from day 1."""
from __future__ import annotations


def test_version_is_set() -> None:
    from app import __version__

    assert __version__
