"""API: visor de Maildir local por cuenta (mismo dato que Dovecot/Roundcube)."""
from __future__ import annotations

import asyncio
import re
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.api.deps import (
    get_client_ip,
    get_db,
    get_user_agent,
    get_user_permissions,
    mailbox_reader_for_path_account,
    require_any_permission,
)
from app.core.config import get_settings
from app.models.accounts import GwAccount
from app.models.enums import AuditAction
from app.models.mailbox_delegation import SysUserMailboxDelegation
from app.models.users import SysUser
from app.schemas.mailbox import (
    GybWorkAccountOut,
    GybWorkMessagesPageOut,
    MailboxAttachmentOut,
    MailboxFolderOut,
    MailboxMessageBodyOut,
    MailboxMessagesPageOut,
    MailboxMessageSummaryOut,
)
from app.services.audit_service import record_audit
from app.services.gyb_work_browser_service import (
    decode_eml_path,
    list_gyb_eml_summaries,
    list_gyb_eml_summaries_for_label,
    list_gyb_gmail_label_folders,
    list_gyb_work_folders,
    read_gyb_eml_leaf_bytes,
    read_gyb_eml_message,
)
from app.services.mail_purge_service import _dir_size, gyb_work_root_for_email
from app.services.mailbox_browser_service import (
    list_maildir_folders,
    list_messages,
    read_message,
    read_message_leaf_bytes,
)
from app.services.maildir_export_service import (
    MaildirExportTooLarge,
    build_maildir_zip_file,
    safe_maildir_zip_stem,
)
from app.services.maildir_paths import maildir_root_for_account
from app.services.maildir_service import gyb_workdir_has_eml_or_mbox

from .accounts import _load, _maildir_ready

router = APIRouter()


@router.get(
    "/gyb-work/accounts",
    response_model=list[GybWorkAccountOut],
    summary="Cuentas con export GYB en carpeta de trabajo (solo .eml/.mbox local)",
)
async def gyb_work_list_accounts(
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_any_permission("mailbox.view_all", "mailbox.view_delegated")),
) -> list[GybWorkAccountOut]:
    stmt = select(GwAccount).order_by(GwAccount.email.asc())
    perms = get_user_permissions(current)
    if "mailbox.view_delegated" in perms and "mailbox.view_all" not in perms:
        stmt = stmt.where(
            GwAccount.id.in_(
                select(SysUserMailboxDelegation.gw_account_id).where(
                    SysUserMailboxDelegation.sys_user_id == current.id
                )
            )
        )
    rows = (await db.execute(stmt)).scalars().all()
    out: list[GybWorkAccountOut] = []
    for a in rows:
        gyb = gyb_work_root_for_email(a.email)
        if not gyb_workdir_has_eml_or_mbox(gyb):
            continue
        out.append(
            GybWorkAccountOut(
                id=str(a.id),
                email=a.email,
                work_size_bytes=_dir_size(gyb) if gyb.is_dir() else None,
                has_msg_db=(gyb / "msg-db.sqlite").is_file(),
            )
        )
    return out


@router.get(
    "/{account_id}/gyb-work/folders",
    response_model=list[MailboxFolderOut],
    summary="Carpetas de trabajo GYB: disco o etiquetas Gmail (msg-db.sqlite)",
)
async def gyb_work_list_folders(
    account_id: uuid.UUID,
    view: Literal["disk", "labels"] = Query(
        "disk",
        description="disk=rutas de directorios con .eml; labels=etiquetas desde msg-db.sqlite",
    ),
    db: AsyncSession = Depends(get_db),
    _u: SysUser = Depends(mailbox_reader_for_path_account),
) -> list[MailboxFolderOut]:
    acc = await _load(db, account_id)
    gyb = gyb_work_root_for_email(acc.email)
    if not gyb_workdir_has_eml_or_mbox(gyb):
        raise HTTPException(status.HTTP_409_CONFLICT, "gyb_work_no_export")
    if view == "labels":
        folders = list_gyb_gmail_label_folders(gyb)
    else:
        folders = list_gyb_work_folders(gyb)
    return [MailboxFolderOut(id=f.folder_id, name=f.display_name) for f in folders]


@router.get(
    "/{account_id}/gyb-work/messages",
    response_model=GybWorkMessagesPageOut,
    summary="Listar .eml por carpeta en disco o por etiqueta Gmail, con búsqueda opcional",
)
async def gyb_work_list_messages(
    account_id: uuid.UUID,
    view: Literal["disk", "labels"] = Query(
        "disk",
        description="disk=param folder; labels=param label (msg-db.sqlite)",
    ),
    folder: str = Query(
        "",
        max_length=2048,
        description="Ruta relativa bajo la raíz GYB (solo vista disk).",
    ),
    label: str = Query(
        "",
        max_length=512,
        description="Nombre de etiqueta Gmail exacto (solo vista labels).",
    ),
    q: str = Query(
        "",
        max_length=200,
        description="Filtrar por texto en asunto o remitente (insensible a mayúsculas).",
    ),
    limit: int = Query(80, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _u: SysUser = Depends(mailbox_reader_for_path_account),
) -> GybWorkMessagesPageOut:
    acc = await _load(db, account_id)
    gyb = gyb_work_root_for_email(acc.email)
    if not gyb_workdir_has_eml_or_mbox(gyb):
        raise HTTPException(status.HTTP_409_CONFLICT, "gyb_work_no_export")
    q_clean = q.strip()
    if view == "labels":
        lab = label.strip()
        if not lab:
            return GybWorkMessagesPageOut(
                view=view,
                folder_id="",
                label="",
                search=q_clean,
                offset=offset,
                limit=limit,
                items=[],
            )
        summaries = list_gyb_eml_summaries_for_label(
            gyb, label=lab, limit=limit, offset=offset, q=q_clean or None
        )
        fid = ""
        lab_out = lab
    else:
        try:
            summaries = list_gyb_eml_summaries(
                gyb,
                folder_id=folder,
                limit=limit,
                offset=offset,
                q=q_clean or None,
            )
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_folder") from exc
        fid = folder.strip()
        lab_out = ""
    return GybWorkMessagesPageOut(
        view=view,
        folder_id=fid,
        label=lab_out,
        search=q_clean,
        offset=offset,
        limit=limit,
        items=[
            MailboxMessageSummaryOut(
                id=x.key,
                subject=x.subject,
                from_=x.from_addr,
                date=x.date_display,
                size=x.size,
            )
            for x in summaries
        ],
    )


@router.get(
    "/{account_id}/gyb-work/message",
    response_model=MailboxMessageBodyOut,
    summary="Leer un .eml de la carpeta de trabajo GYB",
)
async def gyb_work_get_message(
    account_id: uuid.UUID,
    key: str = Query(
        ...,
        min_length=1,
        max_length=4096,
        description="Clave opaca del listado de mensajes",
    ),
    db: AsyncSession = Depends(get_db),
    _u: SysUser = Depends(mailbox_reader_for_path_account),
) -> MailboxMessageBodyOut:
    acc = await _load(db, account_id)
    gyb = gyb_work_root_for_email(acc.email)
    if not gyb_workdir_has_eml_or_mbox(gyb):
        raise HTTPException(status.HTTP_409_CONFLICT, "gyb_work_no_export")
    try:
        body = read_gyb_eml_message(gyb, key=key)
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
        attachments=[
            MailboxAttachmentOut(
                leaf_index=a.leaf_index,
                filename=a.filename,
                content_type=a.content_type,
                size=a.size,
                disposition=a.disposition,
                content_id=a.content_id,
            )
            for a in body.attachments
        ],
    )


@router.get(
    "/{account_id}/gyb-work/attachment",
    summary="Descargar parte MIME de un .eml de carpeta GYB (adjunto)",
    response_class=Response,
)
async def gyb_work_get_attachment_part(
    account_id: uuid.UUID,
    key: str = Query(..., min_length=1, max_length=4096),
    leaf_index: int = Query(..., ge=0, description="Índice de hoja en attachments[].leaf_index"),
    db: AsyncSession = Depends(get_db),
    _u: SysUser = Depends(mailbox_reader_for_path_account),
) -> Response:
    acc = await _load(db, account_id)
    gyb = gyb_work_root_for_email(acc.email).resolve()
    if not gyb_workdir_has_eml_or_mbox(gyb):
        raise HTTPException(status.HTTP_409_CONFLICT, "gyb_work_no_export")
    try:
        path = decode_eml_path(gyb, key)
    except ValueError as exc:
        code = str(exc)
        if code in ("invalid_key", "not_eml"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, code) from exc
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "message_not_found") from exc
    try:
        data, filename, content_type = read_gyb_eml_leaf_bytes(path, leaf_index=leaf_index)
    except ValueError as exc:
        code = str(exc)
        if code in ("invalid_leaf_index", "part_decode_error"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, code) from exc
        if code == "leaf_index_out_of_range":
            raise HTTPException(status.HTTP_404_NOT_FOUND, code) from exc
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    safe = _content_disposition_filename(filename)
    cd = f'attachment; filename="{safe}"'
    return Response(
        content=data,
        media_type=content_type or "application/octet-stream",
        headers={"Content-Disposition": cd},
    )


_ATTACHMENT_FILENAME_SAFE = re.compile(r"[^\w.\- ()\[\]]+")


def _content_disposition_filename(name: str | None) -> str:
    base = (name or "adjunto").strip() or "adjunto"
    base = _ATTACHMENT_FILENAME_SAFE.sub("_", base).strip("._")[:180]
    return base or "adjunto"


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
    q: str = Query("", max_length=400, description="Filtrar por subcadena en asunto o remitente"),
    sort_by: Literal["mtime", "header_date"] = Query(
        "mtime",
        description="mtime=por fecha de fichero (más reciente primero); header_date=por cabecera Date",
    ),
    db: AsyncSession = Depends(get_db),
    _u: SysUser = Depends(mailbox_reader_for_path_account),
) -> MailboxMessagesPageOut:
    acc = await _load(db, account_id)
    root = maildir_root_for_account(acc)
    if not _maildir_ready(root):
        raise HTTPException(status.HTTP_409_CONFLICT, "maildir_not_ready")
    q_strip = q.strip()
    try:
        items = list_messages(
            root,
            folder_id=folder,
            limit=limit,
            offset=offset,
            q=q_strip or None,
            sort_by=sort_by,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return MailboxMessagesPageOut(
        folder_id=folder.strip() or "INBOX",
        offset=offset,
        limit=limit,
        total_estimated=None,
        search=q_strip,
        sort_by=sort_by,
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
        attachments=[
            MailboxAttachmentOut(
                leaf_index=a.leaf_index,
                filename=a.filename,
                content_type=a.content_type,
                size=a.size,
                disposition=a.disposition,
                content_id=a.content_id,
            )
            for a in body.attachments
        ],
    )


@router.get(
    "/{account_id}/mailbox/attachment",
    summary="Descargar una parte del mensaje (adjunto) por índice de hoja MIME",
    response_class=Response,
)
async def mailbox_get_attachment_part(
    account_id: uuid.UUID,
    folder: str = Query("INBOX"),
    key: str = Query(..., min_length=1, max_length=512),
    leaf_index: int = Query(
        ...,
        ge=0,
        description="Índice de parte hoja (attachments[].leaf_index)",
    ),
    db: AsyncSession = Depends(get_db),
    _u: SysUser = Depends(mailbox_reader_for_path_account),
) -> Response:
    acc = await _load(db, account_id)
    root = maildir_root_for_account(acc)
    if not _maildir_ready(root):
        raise HTTPException(status.HTTP_409_CONFLICT, "maildir_not_ready")
    try:
        data, filename, content_type = read_message_leaf_bytes(
            root,
            folder_id=folder,
            message_key=key,
            leaf_index=leaf_index,
        )
    except ValueError as exc:
        code = str(exc)
        if code in ("invalid_message_key", "invalid_leaf_index", "part_decode_error"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, code) from exc
        if code == "leaf_index_out_of_range":
            raise HTTPException(status.HTTP_404_NOT_FOUND, code) from exc
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "message_not_found") from exc

    safe = _content_disposition_filename(filename)
    cd = f'attachment; filename="{safe}"'
    return Response(
        content=data,
        media_type=content_type or "application/octet-stream",
        headers={"Content-Disposition": cd},
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
