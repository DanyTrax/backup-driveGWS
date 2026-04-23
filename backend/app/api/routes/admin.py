"""Platform-level admin operations: git refresh, manual backup, stats."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request
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
from app.services.audit_service import record_audit
from app.services.git_refresh import pull_and_status

router = APIRouter(prefix="/admin", tags=["admin"])

settings = get_settings()


@router.post("/git-refresh")
async def git_refresh(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("platform.refresh")),
) -> dict:
    repo_path = Path("/app")
    result = await pull_and_status(repo_path)
    await record_audit(
        db,
        action=AuditAction.GIT_REFRESH,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        success=bool(result.get("ok")),
        metadata=result,
    )
    await db.commit()
    return result


@router.post("/platform-backup")
async def run_platform_backup(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("platform.backup")),
) -> dict:
    from app.services.platform_backup import run_platform_backup as _run

    result = await _run(db)
    await record_audit(
        db,
        action=AuditAction.PLATFORM_BACKUP,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        success=bool(result.get("ok")),
        metadata=result,
    )
    await db.commit()
    return result
