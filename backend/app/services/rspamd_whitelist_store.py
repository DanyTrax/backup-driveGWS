"""Persistencia y consulta de entradas whitelist Rspamd (panel)."""
from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.rspamd_whitelist import RspamdWhitelistEntry
from app.services.rspamd_whitelist_service import (
    NormalizedWhitelistEntry,
    WhitelistEntryKind,
    WhitelistNormalizeError,
    normalize_whitelist_input,
    parse_env_entry_lines,
)


def row_to_normalized(row: RspamdWhitelistEntry) -> NormalizedWhitelistEntry:
    kind = WhitelistEntryKind(row.kind)
    return NormalizedWhitelistEntry(kind=kind, value=row.value, raw_input=row.raw_input)


async def count_entries(db: AsyncSession) -> int:
    return int((await db.execute(select(func.count()).select_from(RspamdWhitelistEntry))).scalar_one())


async def list_entries(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 25,
    q: str | None = None,
) -> tuple[list[RspamdWhitelistEntry], int]:
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    stmt = select(RspamdWhitelistEntry).options(selectinload(RspamdWhitelistEntry.created_by))
    filters = []
    if q and (term := q.strip()):
        like = f"%{term.lower()}%"
        filters.append(
            or_(
                func.lower(RspamdWhitelistEntry.raw_input).like(like),
                func.lower(RspamdWhitelistEntry.value).like(like),
            )
        )
    count_stmt = select(func.count()).select_from(RspamdWhitelistEntry)
    if filters:
        count_stmt = count_stmt.where(*filters)
        stmt = stmt.where(*filters)
    total = int((await db.execute(count_stmt)).scalar_one())
    stmt = (
        stmt.order_by(RspamdWhitelistEntry.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows), total


async def create_entry(
    db: AsyncSession,
    *,
    raw: str,
    actor_user_id: uuid.UUID | None,
) -> RspamdWhitelistEntry:
    try:
        ent = normalize_whitelist_input(raw)
    except WhitelistNormalizeError as exc:
        raise ValueError(str(exc)) from exc

    existing = (
        await db.execute(
            select(RspamdWhitelistEntry).where(
                RspamdWhitelistEntry.kind == ent.kind.value,
                RspamdWhitelistEntry.value == ent.value,
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise ValueError("duplicate_entry")

    row = RspamdWhitelistEntry(
        raw_input=ent.raw_input,
        kind=ent.kind.value,
        value=ent.value,
        created_by_user_id=actor_user_id,
    )
    db.add(row)
    await db.flush()
    await db.refresh(row, attribute_names=["created_by"])
    return row


async def delete_entries(
    db: AsyncSession,
    *,
    entry_ids: list[uuid.UUID],
) -> int:
    if not entry_ids:
        return 0
    rows = (await db.execute(select(RspamdWhitelistEntry).where(RspamdWhitelistEntry.id.in_(entry_ids)))).scalars().all()
    for row in rows:
        await db.delete(row)
    return len(rows)


async def import_bulk(
    db: AsyncSession,
    *,
    blob: str,
    actor_user_id: uuid.UUID | None,
) -> dict[str, int | list[str]]:
    """Importa reglas separadas por coma o salto de línea."""
    added = 0
    skipped_duplicate = 0
    invalid: list[str] = []
    for chunk in blob.replace(",", "\n").splitlines():
        line = chunk.strip().strip('"').strip("'")
        if not line or line.startswith("#"):
            continue
        try:
            await create_entry(db, raw=line, actor_user_id=actor_user_id)
            added += 1
        except ValueError as exc:
            if str(exc) == "duplicate_entry":
                skipped_duplicate += 1
            else:
                invalid.append(f"{line}: {exc}")
    return {
        "added": added,
        "skipped_duplicate": skipped_duplicate,
        "invalid": invalid,
    }


async def entries_for_feed(
    db: AsyncSession,
    *,
    env_blob: str,
) -> list[NormalizedWhitelistEntry]:
    """BD si hay filas; si no, PoC desde ``RSPAMD_WHITELIST_ENTRIES`` en .env."""
    rows = (await db.execute(select(RspamdWhitelistEntry).order_by(RspamdWhitelistEntry.value.asc()))).scalars().all()
    if rows:
        return [row_to_normalized(r) for r in rows]
    return parse_env_entry_lines(env_blob)
