"""CRUD panel: lista blanca Rspamd (alimenta feeds /security)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
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
    RspamdWhitelistImportIn,
    RspamdWhitelistImportOut,
    RspamdWhitelistListOut,
    RspamdWhitelistUpdateIn,
)
from app.services.audit_service import record_audit
from app.services.rspamd_whitelist_service import WhitelistEntryKind, split_entries
from app.services.rspamd_whitelist_store import (
    count_entries,
    create_entry,
    delete_entries,
    entries_for_feed,
    import_bulk,
    list_entries,
    update_entry,
)

router = APIRouter(prefix="/rspamd-whitelist", tags=["rspamd-whitelist"])


def _entry_out(row) -> RspamdWhitelistEntryOut:
    kind = WhitelistEntryKind(row.kind)
    return RspamdWhitelistEntryOut(
        id=str(row.id),
        raw_input=row.raw_input,
        kind=row.kind,
        value=row.value,
        include_subdomains=bool(getattr(row, "include_subdomains", False)),
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
    source = "database" if await count_entries(db) > 0 else "env"
    return RspamdWhitelistFeedPreviewOut(
        domains=domains,
        emails=emails,
        entry_count=len(entries),
        source=source,
        env_pending_in_db=source == "env" and len(entries) > 0,
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
        row = await create_entry(
            db,
            raw=payload.raw,
            include_subdomains=payload.include_subdomains,
            actor_user_id=current.id,
        )
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


@router.patch("/{entry_id}", response_model=RspamdWhitelistEntryOut)
async def patch_whitelist_entry(
    entry_id: str,
    payload: RspamdWhitelistUpdateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("rspamd_whitelist.edit")),
) -> RspamdWhitelistEntryOut:
    try:
        eid = uuid.UUID(entry_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="invalid_id") from exc

    try:
        row = await update_entry(
            db,
            entry_id=eid,
            raw=payload.raw,
            include_subdomains=payload.include_subdomains,
        )
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
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="entry_not_found")

    await record_audit(
        db,
        action=AuditAction.SETTING_CHANGED,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        target_table="rspamd_whitelist_entries",
        target_id=str(row.id),
        message="rspamd_whitelist_updated",
        metadata={
            "raw": row.raw_input,
            "kind": row.kind,
            "value": row.value,
            "include_subdomains": bool(getattr(row, "include_subdomains", False)),
        },
    )
    await db.commit()
    return _entry_out(row)


@router.post("/import", response_model=RspamdWhitelistImportOut)
async def import_whitelist_entries(
    payload: RspamdWhitelistImportIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("rspamd_whitelist.edit")),
) -> RspamdWhitelistImportOut:
    """Importación masiva: dominios/correos separados por coma o por línea."""
    result = await import_bulk(db, blob=payload.text, actor_user_id=current.id)
    added = int(result["added"])
    if added > 0:
        await record_audit(
            db,
            action=AuditAction.SETTING_CHANGED,
            actor_user_id=current.id,
            actor_label=current.email,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
            target_table="rspamd_whitelist_entries",
            message="rspamd_whitelist_import",
            metadata={
                "added": added,
                "skipped_duplicate": int(result["skipped_duplicate"]),
                "invalid_count": len(result["invalid"]),
            },
        )
    await db.commit()
    return RspamdWhitelistImportOut(
        added=added,
        skipped_duplicate=int(result["skipped_duplicate"]),
        invalid=list(result["invalid"]),
    )


@router.post("/import-from-env", response_model=RspamdWhitelistImportOut)
async def import_whitelist_from_env(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("rspamd_whitelist.edit")),
) -> RspamdWhitelistImportOut:
    """Copia ``RSPAMD_WHITELIST_ENTRIES`` del .env a la base de datos."""
    settings = get_settings()
    blob = (settings.rspamd_whitelist_entries or "").strip()
    if not blob:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "env_empty",
                "message": "RSPAMD_WHITELIST_ENTRIES está vacío en .env.",
            },
        )
    result = await import_bulk(db, blob=blob, actor_user_id=current.id)
    added = int(result["added"])
    if added > 0:
        await record_audit(
            db,
            action=AuditAction.SETTING_CHANGED,
            actor_user_id=current.id,
            actor_label=current.email,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
            target_table="rspamd_whitelist_entries",
            message="rspamd_whitelist_import_from_env",
            metadata={
                "added": added,
                "skipped_duplicate": int(result["skipped_duplicate"]),
            },
        )
    await db.commit()
    return RspamdWhitelistImportOut(
        added=added,
        skipped_duplicate=int(result["skipped_duplicate"]),
        invalid=list(result["invalid"]),
    )


@router.post(
    "/bulk-delete",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
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
