"""Reglas de reutilización de carpeta vault al reactivar backup."""
from __future__ import annotations

from app.services.google.drive import vault_account_root_metadata_ok


def test_reuse_when_folder_under_vault_root() -> None:
    meta = {
        "id": "abc",
        "mimeType": "application/vnd.google-apps.folder",
        "trashed": False,
        "parents": ["vault_root_1"],
    }
    assert vault_account_root_metadata_ok(meta, root_folder_id="vault_root_1") is True


def test_reject_wrong_parent() -> None:
    meta = {
        "id": "abc",
        "mimeType": "application/vnd.google-apps.folder",
        "trashed": False,
        "parents": ["other_root"],
    }
    assert vault_account_root_metadata_ok(meta, root_folder_id="vault_root_1") is False


def test_reject_trashed_or_not_folder() -> None:
    assert (
        vault_account_root_metadata_ok(
            {
                "mimeType": "application/vnd.google-apps.folder",
                "trashed": True,
                "parents": ["vault_root_1"],
            },
            root_folder_id="vault_root_1",
        )
        is False
    )
    assert (
        vault_account_root_metadata_ok(
            {
                "mimeType": "application/vnd.google-apps.document",
                "trashed": False,
                "parents": ["vault_root_1"],
            },
            root_folder_id="vault_root_1",
        )
        is False
    )
    assert vault_account_root_metadata_ok(None, root_folder_id="vault_root_1") is False
