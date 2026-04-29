"""Schemas del visor Maildir (backup local)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class MailboxFolderOut(BaseModel):
    id: str
    name: str


class MailboxMessageSummaryOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    subject: str
    from_: str = Field(alias="from", serialization_alias="from")
    date: str | None = None
    size: int = 0


class MailboxMessagesPageOut(BaseModel):
    folder_id: str
    offset: int
    limit: int
    total_estimated: int | None = None
    items: list[MailboxMessageSummaryOut]


class MailboxMessageBodyOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    subject: str
    from_: str = Field(alias="from", serialization_alias="from")
    date: str | None = None
    text_plain: str | None = None
    text_html: str | None = None
