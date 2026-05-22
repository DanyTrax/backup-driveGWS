"""CRUD panel: lista blanca Rspamd (alimenta feeds /security)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_client_ip,
    get_db,
    get_user_agent,
    require_permission,
)
from app.core.config import get_settings
from app.models.enums import AuditAction
from app.models.users import SysUser
from app.schemas.rspamd_whitelist import (
    RspamdWhitelistBulkDeleteIn,
    RspamdWhitelistCreateIn,
    RspamdWhitelistEntryOut,
    RspamdWhitelistFeedPreviewOut,
    RspamdWhitelistListOut,
)
from app.services.audit_service import record_audit
from app.services.rspamd_whitelist_service import WhitelistEntryKind, split_entries
from app.services.rspamd_whitelist_store import (
    create_entry,
    delete_entries,
    entries_for_feed,
    list_entries,
)

router = APIRouter(prefix="/rspamd-whitelist", tags=["rspamd-whitelist"])


def _entry_out(row) -> RspamdWhitelistEntryOut:
    kind = WhitelistEntryKind(row.kind)
    return RspamdWhitelistEntryOut(
        id=str(row.id),
        raw_input=row.raw_input,
        kind=row.kind,
        value=row.value,
        map_file=(
            "whitelist_dominios.inc"
            if kind == WhitelistEntryKind.domain
            else "whitelist_correos.inc"
        ),
        created_by_email=row.created_by.email if row.created_by else None,
        created_at=row.created_at,
    )


@router.get("", response_model=RspamdWhitelistListOut)
async def list_whitelist_entries(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    q: str | None = Query(None, max_length=200),
    db: AsyncSession = Depends(get_db),
    _u: SysUser = Depends(require_permission("rspamd_whitelist.view")),
) -> RspamdWhitelistListOut:
    rows, total = await list_entries(db, page=page, page_size=page_size, q=q)
    return RspamdWhitelistListOut(
        items=[_entry_out(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/preview", response_model=RspamdWhitelistFeedPreviewOut)
async def feed_preview(
    db: AsyncSession = Depends(get_db),
    _u: SysUser = Depends(require_permission("rspamd_whitelist.view")),
) -> RspamdWhitelistFeedPreviewOut:
    settings = get_settings()
    blob = (settings.rspamd_whitelist_entries or "").strip()
    entries = await entries_for_feed(db, env_blob=blob)
    domains, emails = split_entries(entries)
    host = (settings.domain_platform or "localhost").strip()
    base = f"https://{host}/security"
    base_api = f"https://{host}/api/security"
    from app.services.rspamd_whitelist_store import count_entries

    source = "database" if await count_entries(db) > 0 else "env"
    return RspamdWhitelistFeedPreviewOut(
        domains=domains,
        emails=emails,
        entry_count=len(entries),
        source=source,
        feed_urls={
            "domains_inc": f"{base}/whitelist_dominios.inc?token=***",
            "emails_inc": f"{base}/whitelist_correos.inc?token=***",
            "domains_inc_via_api": f"{base_api}/whitelist_dominios.inc?token=***",
            "emails_inc_via_api": f"{base_api}/whitelist_correos.inc?token=***",
        },
    )


@router.post("", response_model=RspamdWhitelistEntryOut, status_code=status.HTTP_201_CREATED)
async def add_whitelist_entry(
    payload: RspamdWhitelistCreateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("rspamd_whitelist.edit")),
) -> RspamdWhitelistEntryOut:
    try:
        row = await create_entry(db, raw=payload.raw, actor_user_id=current.id)
    except ValueError as exc:
        msg = str(exc)
        if msg == "duplicate_entry":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail={"error": "duplicate_entry", "message": "Esa regla ya existe en la lista."},
            ) from exc
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_entry", "message": msg},
        ) from exc

    await record_audit(
        db,
        action=AuditAction.SETTING_CHANGED,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        target_table="rspamd_whitelist_entries",
        target_id=str(row.id),
        message="rspamd_whitelist_added",
        metadata={"raw": row.raw_input, "kind": row.kind, "value": row.value},
    )
    await db.commit()
    return _entry_out(row)


@router.post("/bulk-delete", status_code=status.HTTP_204_NO_CONTENT)
async def bulk_delete_whitelist_entries(
    payload: RspamdWhitelistBulkDeleteIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("rspamd_whitelist.edit")),
) -> None:
    try:
        ids = [uuid.UUID(x) for x in payload.ids]
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="invalid_id") from exc

    deleted = await delete_entries(db, entry_ids=ids)
    if deleted:
        await record_audit(
            db,
            action=AuditAction.SETTING_CHANGED,
            actor_user_id=current.id,
            actor_label=current.email,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
            target_table="rspamd_whitelist_entries",
            message="rspamd_whitelist_deleted",
            metadata={"ids": payload.ids, "count": deleted},
        )
    await db.commit()
