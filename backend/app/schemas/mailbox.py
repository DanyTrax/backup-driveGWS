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
    search: str = ""
    sort_by: str = "mtime"
    items: list[MailboxMessageSummaryOut]


class MailboxAttachmentOut(BaseModel):
    """Parte descargable: ``leaf_index`` coincide con ``GET .../mailbox/attachment``."""

    leaf_index: int
    filename: str | None = None
    content_type: str
    size: int = 0
    disposition: str | None = None
    content_id: str | None = None


class MailboxMessageBodyOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    subject: str
    from_: str = Field(alias="from", serialization_alias="from")
    date: str | None = None
    text_plain: str | None = None
    text_html: str | None = None
    attachments: list[MailboxAttachmentOut] = Field(default_factory=list)


class GybWorkAccountOut(BaseModel):
    """Cuenta con export ``.eml``/``.mbox`` en la carpeta de trabajo GYB local."""

    id: str
    email: str
    work_size_bytes: int | None = None
    has_msg_db: bool = False


class GybWorkMessagesPageOut(BaseModel):
    """Mensajes ``.eml`` en carpeta de disco o bajo una etiqueta Gmail (vía ``msg-db.sqlite``)."""

    view: str = "disk"
    folder_id: str = ""
    label: str = ""
    search: str = ""
    offset: int
    limit: int
    items: list[MailboxMessageSummaryOut]
