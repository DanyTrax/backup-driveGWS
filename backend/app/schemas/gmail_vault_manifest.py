"""Manifiesto JSON v1 para ZIPs bajo ``1-GMAIL/zips/`` (Fase 2).

Validar con ``GmailVaultZipManifestV1.model_validate``; serializar con ``model_dump(mode=\"json\")``.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MANIFEST_VERSION: Literal[1] = 1


class GmailVaultManifestFileEntry(BaseModel):
    """Un archivo empaquetado dentro del ZIP (ruta relativa al root del zip)."""

    model_config = ConfigDict(extra="forbid")

    rel_path: str = Field(min_length=1, max_length=2048)
    size_bytes: int = Field(ge=0)
    sha256: Optional[str] = Field(default=None, min_length=64, max_length=64)

    @field_validator("rel_path")
    @classmethod
    def _no_abs(cls, v: str) -> str:
        s = v.replace("\\", "/").strip()
        if s.startswith("/") or s.startswith(".."):
            raise ValueError("rel_path must be relative and must not start with ..")
        return s


SealKind = Literal["bootstrap", "weekly", "monthly", "manual"]


class GmailVaultZipManifestV1(BaseModel):
    """Contrato v1 entre worker, vault en Drive y visor (materialización)."""

    model_config = ConfigDict(extra="forbid")

    manifest_version: Literal[1] = Field(default=1)
    account_id: uuid.UUID
    account_email: str = Field(min_length=3, max_length=255)
    task_id: Optional[uuid.UUID] = None
    timezone: str = Field(default="America/Bogota", max_length=64)
    period_start: date
    period_end: date
    overlap_days_applied: int = Field(default=0, ge=0, le=366)
    seal_kind: SealKind
    gmail_watermark: dict[str, Any] = Field(default_factory=dict)
    backup_log_id: Optional[uuid.UUID] = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Instante UTC de creación del manifiesto.",
    )
    gyb_version_note: Optional[str] = Field(default=None, max_length=500)
    zip_basename: Optional[str] = Field(
        default=None,
        max_length=256,
        description="Nombre de archivo del zip asociado (sin directorio), p. ej. 2026-05-01__2026-05-07.zip",
    )
    files: list[GmailVaultManifestFileEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def _period_order(self) -> GmailVaultZipManifestV1:
        if self.period_end < self.period_start:
            raise ValueError("period_end must be >= period_start")
        return self


def parse_gmail_vault_manifest(data: dict[str, Any]) -> GmailVaultZipManifestV1:
    """Parsea dict (p. ej. desde JSON); falla si ``manifest_version`` no es 1."""
    v = data.get("manifest_version")
    if v != 1:
        raise ValueError(f"unsupported manifest_version: {v!r}, expected 1")
    return GmailVaultZipManifestV1.model_validate(data)
