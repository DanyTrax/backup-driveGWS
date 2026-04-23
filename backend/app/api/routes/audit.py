"""Audit log viewer (read-only)."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_permission
from app.models.audit import SysAudit

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditOut(BaseModel):
    id: str
    created_at: datetime
    actor_user_id: str | None
    actor_label: str | None
    action: str
    target_table: str | None
    target_id: str | None
    ip_address: str | None
    success: bool
    message: str | None
    metadata: dict | None


def _to_out(a: SysAudit) -> AuditOut:
    return AuditOut(
        id=str(a.id),
        created_at=a.created_at,
        actor_user_id=str(a.actor_user_id) if a.actor_user_id else None,
        actor_label=a.actor_label,
        action=a.action,
        target_table=a.target_table,
        target_id=a.target_id,
        ip_address=str(a.ip_address) if a.ip_address else None,
        success=a.success,
        message=a.message,
        metadata=a.metadata_json,
    )


@router.get("", response_model=list[AuditOut])
async def list_audit(
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    action: str | None = None,
    actor_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _u=Depends(require_permission("audit.view")),
) -> list[AuditOut]:
    stmt = select(SysAudit).order_by(SysAudit.created_at.desc()).limit(limit).offset(offset)
    if action:
        stmt = stmt.where(SysAudit.action == action)
    if actor_id:
        stmt = stmt.where(SysAudit.actor_user_id == actor_id)
    rows = (await db.execute(stmt)).scalars().all()
    return [_to_out(r) for r in rows]
