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


@router.post("/git-refresh")
async def git_refresh(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("platform.refresh")),
) -> dict:
    cfg = get_settings()
    repo_path = Path(cfg.git_working_tree)
    if not (repo_path / ".git").is_dir():
        result = {
            "ok": False,
            "error": "not_a_git_repository",
            "hint": (
                "En la imagen Docker el código se copia sin carpeta .git. "
                "Actualizá en el servidor con: cd /opt/stacks/backup-stack && git pull "
                "&& cd docker && docker compose up -d --build. "
                "Opcional: montá un clon del repo con .git y definí GIT_WORKING_TREE en .env."
            ),
        }
        await record_audit(
            db,
            action=AuditAction.GIT_REFRESH,
            actor_user_id=current.id,
            actor_label=current.email,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
            success=False,
            metadata=result,
        )
        await db.commit()
        return result
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

    try:
        result = await _run(db)
    except Exception as exc:
        result = {
            "ok": False,
            "error": "platform_backup_exception",
            "reason": str(exc)[:800],
        }
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
