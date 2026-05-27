"""Schemas API para pools de bóveda y asignación por cuenta."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

VaultMode = Literal["default", "pool", "dedicated"]


class VaultPoolOut(BaseModel):
    id: str
    name: str
    shared_drive_id: str
    root_folder_id: str
    description: str | None = None
    account_count: int = 0
    created_at: datetime


class VaultPoolCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    shared_drive_id: str = Field(..., min_length=4, max_length=128)
    root_folder_id: str = Field(..., min_length=4, max_length=128)
    description: str | None = Field(default=None, max_length=2000)


class VaultPoolUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    shared_drive_id: str | None = Field(default=None, min_length=4, max_length=128)
    root_folder_id: str | None = Field(default=None, min_length=4, max_length=128)
    description: str | None = Field(default=None, max_length=2000)


class AccountVaultAssignmentIn(BaseModel):
    vault_mode: VaultMode
    vault_pool_id: str | None = None
    reprovision: bool = True


class AccountVaultAssignmentOut(BaseModel):
    account_id: str
    email: str
    vault_mode: str
    vault_pool_id: str | None = None
    vault_pool_name: str | None = None
    dedicated_shared_drive_id: str | None = None
    drive_vault_folder_id: str | None = None
    vault_label: str
