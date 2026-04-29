"""API: visor de Maildir local por cuenta (mismo dato que Dovecot/Roundcube)."""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.api.deps import get_client_ip, get_db, get_user_agent, mailbox_reader_for_path_account
from app.core.config import get_settings
from app.models.enums import AuditAction
from app.models.users import SysUser
from app.services.audit_service import record_audit
from app.services.maildir_export_service import (
    MaildirExportTooLarge,
    build_maildir_zip_file,
    safe_maildir_zip_stem,
)
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


def _unlink_zip_path(p: Path) -> None:
    try:
        p.unlink(missing_ok=True)
    except OSError:
        pass


@router.get(
    "/{account_id}/mailbox/maildir-export.zip",
    summary="Descargar ZIP del Maildir local (copia del backup en disco)",
    response_class=FileResponse,
)
async def mailbox_maildir_export_zip(
    account_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(mailbox_reader_for_path_account),
) -> FileResponse:
    """Empaqueta el árbol Maildir actual (carpetas .Label, cur/new/tmp, etc.) en un ``.zip``.

    Misma autorización que el visor Maildir. Puede tardar bastante en buzones grandes; ajustá
    ``MAILDIR_EXPORT_MAX_BYTES`` en ``.env`` si querés un tope (0 = sin tope).
    """
    acc = await _load(db, account_id)
    root = maildir_root_for_account(acc)
    if not _maildir_ready(root):
        raise HTTPException(status.HTTP_409_CONFLICT, "maildir_not_ready")

    settings = get_settings()
    max_b = settings.maildir_export_max_bytes

    try:
        zip_path = await asyncio.to_thread(
            lambda: build_maildir_zip_file(root, max_total_bytes=max_b),
        )
    except MaildirExportTooLarge as exc:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "error": "maildir_export_too_large",
                "limit": exc.limit,
                "would_total": exc.would_total,
            },
        ) from exc

    stem = safe_maildir_zip_stem(acc.email)
    filename = f"{stem}_maildir.zip"

    await record_audit(
        db,
        action=AuditAction.SETTING_CHANGED,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        target_table="gw_accounts",
        target_id=str(acc.id),
        message="maildir_zip_exported",
        metadata={"email": acc.email, "filename": filename},
    )
    await db.commit()

    return FileResponse(
        path=str(zip_path),
        filename=filename,
        media_type="application/zip",
        background=BackgroundTask(_unlink_zip_path, zip_path),
    )
