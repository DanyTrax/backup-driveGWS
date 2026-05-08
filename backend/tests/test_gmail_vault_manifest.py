"""Tests manifiesto ZIP Gmail v1 y layout de rutas bajo 1-GMAIL/zips."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest

from app.schemas.gmail_vault_manifest import (
    GmailVaultManifestFileEntry,
    GmailVaultZipManifestV1,
    parse_gmail_vault_manifest,
)
from app.services.gmail_vault_zip_layout import (
    gmail_vault_zip_and_manifest_rel,
    gmail_vault_zips_root_rel,
    manifest_basename_for_zip,
    parse_zip_basename_period,
    seal_kind_to_zip_cadence_dir,
    zip_basename_for_period,
)


def test_zip_basename_roundtrip_period() -> None:
    z = zip_basename_for_period(date(2026, 5, 1), date(2026, 5, 7))
    assert z == "2026-05-01__2026-05-07.zip"
    assert manifest_basename_for_zip(z) == "2026-05-01__2026-05-07.manifest.json"
    parsed = parse_zip_basename_period(z)
    assert parsed == (date(2026, 5, 1), date(2026, 5, 7))


def test_parse_zip_basename_invalid() -> None:
    assert parse_zip_basename_period("other.zip") is None
    assert parse_zip_basename_period("2026-05-02__2026-05-01.zip") is None


def test_gmail_vault_zips_root_rel() -> None:
    assert gmail_vault_zips_root_rel() == "1-GMAIL/zips"


def test_manifest_validate_and_parse_roundtrip() -> None:
    aid = uuid.uuid4()
    tid = uuid.uuid4()
    lid = uuid.uuid4()
    m = GmailVaultZipManifestV1(
        account_id=aid,
        account_email="u@example.com",
        task_id=tid,
        timezone="America/Bogota",
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 7),
        overlap_days_applied=1,
        seal_kind="weekly",
        gmail_watermark={"history_id": "123"},
        backup_log_id=lid,
        created_at=datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc),
        zip_basename="2026-05-01__2026-05-07.zip",
        files=[GmailVaultManifestFileEntry(rel_path="msg/a.eml", size_bytes=10, sha256=None)],
    )
    dump = m.model_dump(mode="json")
    assert dump["manifest_version"] == 1
    m2 = parse_gmail_vault_manifest(dump)
    assert m2.account_id == aid
    assert m2.files[0].rel_path == "msg/a.eml"


def test_gmail_vault_zip_and_manifest_rel_paths() -> None:
    aid = uuid.uuid4()
    z, mj = gmail_vault_zip_and_manifest_rel(
        aid,
        "WEEKLY",
        date(2026, 5, 1),
        date(2026, 5, 7),
    )
    assert z.endswith("2026-05-01__2026-05-07.zip")
    assert mj.endswith("2026-05-01__2026-05-07.manifest.json")
    assert str(aid) in z and str(aid) in mj


def test_seal_kind_to_zip_cadence_dir() -> None:
    assert seal_kind_to_zip_cadence_dir("weekly") == "WEEKLY"
    with pytest.raises(ValueError):
        seal_kind_to_zip_cadence_dir("unknown")


def test_manifest_rejects_bad_period() -> None:
    with pytest.raises(ValueError):
        GmailVaultZipManifestV1(
            account_id=uuid.uuid4(),
            account_email="u@example.com",
            period_start=date(2026, 5, 8),
            period_end=date(2026, 5, 1),
            seal_kind="weekly",
        )


def test_manifest_rejects_bad_rel_path() -> None:
    with pytest.raises(ValueError):
        GmailVaultZipManifestV1(
            account_id=uuid.uuid4(),
            account_email="u@example.com",
            period_start=date(2026, 5, 1),
            period_end=date(2026, 5, 1),
            seal_kind="weekly",
            files=[GmailVaultManifestFileEntry(rel_path="../x.eml", size_bytes=1)],
        )


def test_parse_manifest_version_mismatch() -> None:
    with pytest.raises(ValueError, match="unsupported manifest_version"):
        parse_gmail_vault_manifest({"manifest_version": 2})
