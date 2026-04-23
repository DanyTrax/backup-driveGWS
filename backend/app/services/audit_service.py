"""Helpers to record entries in the append-only audit log."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import SysAudit
from app.models.enums import AuditAction


async def record_audit(
    db: AsyncSession,
    *,
    action: AuditAction | str,
    actor_user_id: uuid.UUID | str | None = None,
    actor_label: str | None = None,
    target_table: str | None = None,
    target_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    success: bool = True,
    message: str | None = None,
    metadata: dict[str, Any] | None = None,
    commit: bool = False,
) -> SysAudit:
    entry = SysAudit(
        actor_user_id=uuid.UUID(str(actor_user_id)) if actor_user_id else None,
        actor_label=actor_label,
        action=action.value if isinstance(action, AuditAction) else str(action),
        target_table=target_table,
        target_id=target_id,
        ip_address=ip_address,
        user_agent=(user_agent or "")[:400] or None,
        success=success,
        message=message,
        metadata_json=metadata,
    )
    db.add(entry)
    await db.flush()
    if commit:
        await db.commit()
    return entry
