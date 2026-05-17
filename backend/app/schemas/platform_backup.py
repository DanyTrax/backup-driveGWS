"""Schemas para contexto y operaciones de respaldo de plataforma."""
from __future__ import annotations

from pydantic import BaseModel, Field


class PlatformBackupDriveFileOut(BaseModel):
    id: str
    name: str
    created_time: str | None = None


class PlatformBackupContextOut(BaseModel):
    vault_configured: bool
    shared_drive_id: str | None = None
    shared_drive_name: str | None = None
    vault_root_folder_id: str | None = None
    platform_backup_folder_id: str | None = None
    folder_url: str | None = Field(default=None, description="Enlace a la carpeta Platform-Backups en Drive")
    vault_root_url: str | None = None
    recent_backups: list[PlatformBackupDriveFileOut] = Field(default_factory=list)
    includes_summary: str = ""
    incoming_path_container: str = "/platform_backups/incoming"


class PlatformBackupUploadOut(BaseModel):
    ok: bool
    local_path: str | None = None
    drive_file_id: str | None = None
    error: str | None = None
