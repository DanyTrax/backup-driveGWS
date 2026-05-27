"""Tests aprovisionamiento automático de pools (sin Google API)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.vault_pool_store import provision_pool_in_google


@pytest.mark.asyncio
async def test_provision_pool_in_google_registers_row() -> None:
    db = AsyncMock()

    async def fake_assert(_db, _name, *, exclude_id=None):
        return None

    with (
        patch("app.services.vault_pool_store._assert_unique_pool_name", side_effect=fake_assert),
        patch(
            "app.services.vault_pool_store.create_shared_drive",
            new_callable=AsyncMock,
            return_value={"id": "drive-abc", "name": "MSA Backup — P2"},
        ),
        patch(
            "app.services.vault_pool_store.add_service_account_to_shared_drive",
            new_callable=AsyncMock,
        ),
        patch(
            "app.services.vault_pool_store.ensure_folder",
            new_callable=AsyncMock,
            return_value={"id": "folder-root", "name": "BackupRoot"},
        ),
        patch(
            "app.services.vault_pool_store.check_shared_drive",
            new_callable=AsyncMock,
            return_value={"ok": True},
        ),
    ):
        row = await provision_pool_in_google(db, name="Pool 2", description="test")

    assert row.name == "Pool 2"
    assert row.shared_drive_id == "drive-abc"
    assert row.root_folder_id == "folder-root"
    db.add.assert_called_once()
    db.flush.assert_awaited()
