"""Smoke tests for Phase 2 data model."""
from __future__ import annotations

import os

os.environ.setdefault("SECRET_KEY", "a" * 64)
os.environ.setdefault("FERNET_KEY", "X4R0fXsPI_dKv-EbN8JxW7zKdOqmRVcAjUPblhMx7eg=")
os.environ.setdefault("POSTGRES_USER", "ci")
os.environ.setdefault("POSTGRES_PASSWORD", "ci")
os.environ.setdefault("POSTGRES_DB", "ci")


EXPECTED_TABLES = {
    "sys_roles",
    "sys_permissions",
    "sys_role_permissions",
    "sys_users",
    "sys_sessions",
    "sys_audit",
    "sys_settings",
    "gw_accounts",
    "gw_sync_log",
    "backup_tasks",
    "backup_task_accounts",
    "backup_logs",
    "restore_jobs",
    "webmail_access_tokens",
    "notifications",
    "sys_user_notification_prefs",
    "sys_user_mailbox_delegations",
}


def test_all_expected_tables_registered() -> None:
    from app.models import Base

    present = set(Base.metadata.tables.keys())
    missing = EXPECTED_TABLES - present
    assert not missing, f"Missing tables: {missing}"


def test_sys_users_has_mfa_and_lockout_columns() -> None:
    from app.models import Base

    cols = set(Base.metadata.tables["sys_users"].columns.keys())
    assert {"mfa_enabled", "mfa_secret_encrypted", "failed_login_count", "locked_until"} <= cols


def test_gw_accounts_has_imap_and_vault_columns() -> None:
    from app.models import Base

    cols = set(Base.metadata.tables["gw_accounts"].columns.keys())
    assert {
        "imap_enabled",
        "imap_password_hash",
        "imap_locked_until",
        "maildir_path",
        "maildir_user_cleared_at",
        "drive_vault_folder_id",
        "is_backup_enabled",
        "org_unit_path",
    } <= cols


def test_backup_logs_tracks_rclone_rc_and_checksum() -> None:
    from app.models import Base

    cols = set(Base.metadata.tables["backup_logs"].columns.keys())
    assert {
        "pid",
        "rclone_rc_port",
        "rclone_job_id",
        "sha256_manifest_path",
        "celery_task_id",
        "run_batch_id",
        "gmail_maildir_ready_at",
        "gmail_vault_completed_at",
    } <= cols


def test_permissions_catalog_is_consistent() -> None:
    from app.core.permissions_catalog import DEFAULT_ROLE_PERMISSIONS, PERMISSIONS
    from app.models.enums import UserRole

    all_codes = {p.code for p in PERMISSIONS}
    # Every permission listed in DEFAULT_ROLE_PERMISSIONS must exist in the catalog.
    for role, codes in DEFAULT_ROLE_PERMISSIONS.items():
        unknown = codes - all_codes
        assert not unknown, f"role {role} references unknown permissions: {unknown}"

    # All three built-in roles must be present.
    assert set(DEFAULT_ROLE_PERMISSIONS.keys()) == set(UserRole)

    # SuperAdmin must have every permission.
    assert DEFAULT_ROLE_PERMISSIONS[UserRole.SUPER_ADMIN] == frozenset(all_codes)


def test_crypto_roundtrip() -> None:
    from app.core.crypto import decrypt_str, encrypt_str

    ciphertext = encrypt_str("hello world")
    assert ciphertext != "hello world"
    assert decrypt_str(ciphertext) == "hello world"


def test_sys_setting_wraps_secret_with_fernet() -> None:
    from app.models.settings import SysSetting

    s = SysSetting(key="google_sa_json", is_secret=True)
    s.set_plaintext("{\"foo\":\"bar\"}")
    assert s.value and s.value != "{\"foo\":\"bar\"}"
    assert s.get_plaintext() == "{\"foo\":\"bar\"}"


def test_sys_setting_skips_crypto_when_not_secret() -> None:
    from app.models.settings import SysSetting

    s = SysSetting(key="platform_public_url", is_secret=False)
    s.set_plaintext("https://example.com")
    assert s.value == "https://example.com"
    assert s.get_plaintext() == "https://example.com"
