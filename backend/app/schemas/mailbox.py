"""Schemas del visor Maildir (backup local)."""
from __future__ import annotations

from datetime import datetime

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
    """Etiquetas Gmail (msg-db) cuando el listado es vista ``labels``; vacío en Maildir/disco puro."""
    labels: list[str] = Field(default_factory=list)


class MailboxMessagesPageOut(BaseModel):
    folder_id: str
    offset: int
    limit: int
    total_estimated: int | None = None
    search: str = ""
    sort_by: str = "header_date"
    sort_order: str = "desc"
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
    """Bytes recorriendo todo el árbol local (solo si ``with_work_sizes`` en el listado)."""
    has_msg_db: bool = False
    estimated_export_bytes: int | None = None
    """Mejor estimación del peso del export (último backup/restauración Gmail exitoso, o caché en cuenta)."""
    estimated_messages: int | None = None
    estimated_at: datetime | None = None
    """Momento de cierre del log elegido (backup/restauración) o último backup exitoso en caché de cuenta."""
    estimated_source: str | None = None
    """``backup_log`` | ``restore_job`` | ``gw_account_cache`` — origen de ``estimated_*``."""


class GybWorkMessagesPageOut(BaseModel):
    """Mensajes ``.eml`` en carpeta de disco o bajo una etiqueta Gmail (vía ``msg-db.sqlite``)."""

    view: str = "disk"
    folder_id: str = ""
    label: str = ""
    search: str = ""
    list_scope: str = "folder"
    sort_by: str = "header_date"
    sort_order: str = "desc"
    offset: int
    limit: int
    has_more: bool = False
    """Total de mensajes en el alcance (sin filtro de búsqueda)."""
    total_in_scope: int | None = None
    """Total que coincide con la búsqueda (igual a ``total_in_scope`` si no hay ``q``)."""
    total_matches: int | None = None
    items: list[MailboxMessageSummaryOut]
