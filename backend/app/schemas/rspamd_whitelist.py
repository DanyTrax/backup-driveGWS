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


class RspamdWhitelistFeedPreviewOut(BaseModel):
    domains: list[str]
    emails: list[str]
    entry_count: int
    source: str
    feed_urls: dict[str, str]
