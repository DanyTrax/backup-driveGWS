"""Variables RCLONE_GMAIL_VAULT_* tolerantes a .env incompleto (evita caída del contenedor / 502)."""
from __future__ import annotations

import pytest
from pydantic_settings import SettingsConfigDict

from app.core import config as config_module


class _FreshSettings(config_module.Settings):
    """Settings sin leer .env del disco para tests."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=False)


@pytest.fixture
def minimal_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    monkeypatch.setenv("FERNET_KEY", "7VI2LAMoVGr1qa7W3lUJDmfnGbcH-I_wfQ0bFnfZAPg=")
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")
    monkeypatch.setenv("POSTGRES_DB", "d")


def test_gmail_vault_empty_int_env_uses_defaults(minimal_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RCLONE_GMAIL_VAULT_TRANSFERS", "")
    monkeypatch.setenv("RCLONE_GMAIL_VAULT_CHECKERS", "   ")
    monkeypatch.setenv("RCLONE_GMAIL_VAULT_TPSLIMIT", "")
    monkeypatch.setenv("RCLONE_GMAIL_VAULT_TPSLIMIT_BURST", "")
    s = _FreshSettings()  # type: ignore[call-arg]
    assert s.rclone_gmail_vault_transfers == config_module._GV_TRANSFERS
    assert s.rclone_gmail_vault_checkers == config_module._GV_CHECKERS
    assert s.rclone_gmail_vault_tpslimit == 0
    assert s.rclone_gmail_vault_tpslimit_burst == 0


def test_gmail_vault_compare_invalid_coerces_to_size_only(
    minimal_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RCLONE_GMAIL_VAULT_COMPARE", "not_a_mode")
    s = _FreshSettings()  # type: ignore[call-arg]
    assert s.rclone_gmail_vault_compare == "size_only"


def test_gmail_vault_no_traverse_si_is_true(minimal_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RCLONE_GMAIL_VAULT_NO_TRAVERSE", "si")
    s = _FreshSettings()  # type: ignore[call-arg]
    assert s.rclone_gmail_vault_no_traverse is True
