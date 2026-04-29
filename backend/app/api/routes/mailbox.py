"""API: visor de Maildir local por cuenta (mismo dato que Dovecot/Roundcube)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, mailbox_reader_for_path_account
from app.models.users import SysUser
from app.schemas.mailbox import (
    MailboxFolderOut,
    MailboxMessageBodyOut,
    MailboxMessagesPageOut,
    MailboxMessageSummaryOut,
)
from app.services.mailbox_browser_service import (
    list_maildir_folders,
    list_messages,
    read_message,
)
from app.services.maildir_paths import maildir_root_for_account

from .accounts import _load, _maildir_ready

router = APIRouter()


@router.get(
    "/{account_id}/mailbox/folders",
    response_model=list[MailboxFolderOut],
    summary="Listar carpetas Maildir locales",
)
async def mailbox_list_folders(
    account_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _u: SysUser = Depends(mailbox_reader_for_path_account),
) -> list[MailboxFolderOut]:
    acc = await _load(db, account_id)
    root = maildir_root_for_account(acc)
    if not _maildir_ready(root):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "maildir_not_ready",
        )
    return [MailboxFolderOut(id=i, name=n) for i, n in list_maildir_folders(root)]


@router.get(
    "/{account_id}/mailbox/messages",
    response_model=MailboxMessagesPageOut,
    summary="Listar mensajes de una carpeta Maildir",
)
async def mailbox_list_messages(
    account_id: uuid.UUID,
    folder: str = Query("INBOX", description="Id de carpeta (INBOX o .Nombre)"),
    limit: int = Query(80, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _u: SysUser = Depends(mailbox_reader_for_path_account),
) -> MailboxMessagesPageOut:
    acc = await _load(db, account_id)
    root = maildir_root_for_account(acc)
    if not _maildir_ready(root):
        raise HTTPException(status.HTTP_409_CONFLICT, "maildir_not_ready")
    try:
        items = list_messages(root, folder_id=folder, limit=limit, offset=offset)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return MailboxMessagesPageOut(
        folder_id=folder.strip() or "INBOX",
        offset=offset,
        limit=limit,
        total_estimated=None,
        items=[
            MailboxMessageSummaryOut(
                id=x.key,
                subject=x.subject,
                from_=x.from_addr,
                date=x.date_display,
                size=x.size,
            )
            for x in items
        ],
    )


@router.get(
    "/{account_id}/mailbox/message",
    response_model=MailboxMessageBodyOut,
    summary="Leer un mensaje Maildir (cuerpo)",
)
async def mailbox_get_message(
    account_id: uuid.UUID,
    folder: str = Query("INBOX"),
    key: str = Query(..., min_length=1, max_length=512, description="Nombre de fichero en cur/new"),
    db: AsyncSession = Depends(get_db),
    _u: SysUser = Depends(mailbox_reader_for_path_account),
) -> MailboxMessageBodyOut:
    acc = await _load(db, account_id)
    root = maildir_root_for_account(acc)
    if not _maildir_ready(root):
        raise HTTPException(status.HTTP_409_CONFLICT, "maildir_not_ready")
    try:
        body = read_message(root, folder_id=folder, message_key=key)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "message_not_found") from exc
    return MailboxMessageBodyOut(
        id=body.key,
        subject=body.subject,
        from_=body.from_addr,
        date=body.date_display,
        text_plain=body.text_plain,
        text_html=body.text_html,
    )
