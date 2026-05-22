"""Schemas API lista blanca Rspamd."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RspamdWhitelistEntryOut(BaseModel):
    id: str
    raw_input: str
    kind: str
    value: str
    map_file: str
    created_by_email: str | None = None
    created_at: datetime


class RspamdWhitelistListOut(BaseModel):
    items: list[RspamdWhitelistEntryOut]
    total: int
    page: int
    page_size: int


class RspamdWhitelistCreateIn(BaseModel):
    raw: str = Field(..., min_length=1, max_length=320)


class RspamdWhitelistBulkDeleteIn(BaseModel):
    ids: list[str] = Field(..., min_length=1)


class RspamdWhitelistImportIn(BaseModel):
    """Texto con reglas separadas por coma o una por línea."""

    text: str = Field(..., min_length=1, max_length=50000)


class RspamdWhitelistImportOut(BaseModel):
    added: int
    skipped_duplicate: int
    invalid: list[str] = Field(default_factory=list)


class RspamdWhitelistFeedPreviewOut(BaseModel):
    domains: list[str]
    emails: list[str]
    entry_count: int
    source: str
    #: True si el feed sale del .env y la tabla del panel aún está vacía.
    env_pending_in_db: bool = False
    feed_urls: dict[str, str]
