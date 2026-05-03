"""API schemas — explorador de bóveda Drive."""
from __future__ import annotations

from pydantic import BaseModel, Field


class VaultDriveItemOut(BaseModel):
    id: str
    name: str
    mime_type: str
    is_folder: bool
    size: int | None = None
    modified_time: str | None = None
    web_view_link: str | None = None


class VaultDriveChildrenPageOut(BaseModel):
    items: list[VaultDriveItemOut]
    next_page_token: str | None = None


class VaultDriveSearchOut(BaseModel):
    items: list[VaultDriveItemOut]
    truncated: bool = False


class VaultDriveAccountOut(BaseModel):
    id: str
    email: str
