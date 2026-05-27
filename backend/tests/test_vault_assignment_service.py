"""Tests resolución de bóveda por cuenta (sin Google API)."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.models.accounts import GwAccount
from app.models.vault_pool import VaultPool
from app.services.vault_assignment_service import (
    VAULT_MODE_DEFAULT,
    VAULT_MODE_DEDICATED,
    VAULT_MODE_POOL,
    VaultAssignmentError,
    resolve_vault_target,
)


@pytest.mark.asyncio
async def test_resolve_default_vault() -> None:
    acc = GwAccount(email="u@x.com", vault_mode=VAULT_MODE_DEFAULT)
    db = AsyncMock()

    async def fake_get(_db, key):
        if key.endswith("shared_drive_id"):
            return "drive-global"
        if key.endswith("root_folder_id"):
            return "root-global"
        return ""

    with patch(
        "app.services.vault_assignment_service.get_value",
        side_effect=fake_get,
    ):
        target = await resolve_vault_target(db, acc)
    assert target.shared_drive_id == "drive-global"
    assert target.layout_parent_id == "root-global"


@pytest.mark.asyncio
async def test_resolve_pool_vault() -> None:
    pool_id = uuid.uuid4()
    pool = VaultPool(
        name="Pool 2",
        shared_drive_id="drive-pool",
        root_folder_id="root-pool",
    )
    pool.id = pool_id
    acc = GwAccount(email="u@x.com", vault_mode=VAULT_MODE_POOL, vault_pool_id=pool_id)
    db = AsyncMock()
    result = AsyncMock()
    result.scalar_one_or_none = lambda: pool
    db.execute = AsyncMock(return_value=result)
    target = await resolve_vault_target(db, acc)
    assert target.shared_drive_id == "drive-pool"
    assert target.layout_parent_id == "root-pool"


@pytest.mark.asyncio
async def test_resolve_dedicated_requires_drive_id() -> None:
    acc = GwAccount(email="u@x.com", vault_mode=VAULT_MODE_DEDICATED)
    db = AsyncMock()
    with pytest.raises(VaultAssignmentError):
        await resolve_vault_target(db, acc)
