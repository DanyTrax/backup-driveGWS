"""Platform-level admin operations: git refresh, manual backup, stats."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_client_ip,
    get_db,
    get_user_agent,
    require_any_permission,
    require_permission,
)
from app.core.config import get_settings
from app.models.enums import AuditAction
from app.models.users import SysUser
from app.schemas.platform_backup import (
    PlatformBackupContextOut,
    PlatformBackupUploadOut,
)
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


@router.get("/platform-backup/context", response_model=PlatformBackupContextOut)
async def platform_backup_context(
    db: AsyncSession = Depends(get_db),
    _: SysUser = Depends(require_any_permission("platform.backup", "restore.view")),
) -> PlatformBackupContextOut:
    from app.services.platform_backup import get_platform_backup_context

    data = await get_platform_backup_context(db)
    return PlatformBackupContextOut.model_validate(data)


@router.post("/platform-backup/upload", response_model=PlatformBackupUploadOut)
async def platform_backup_upload(
    request: Request,
    file: UploadFile = File(...),
    also_upload_to_drive: bool = Form(True),
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("platform.backup")),
) -> PlatformBackupUploadOut:
    from app.services.platform_backup import (
        MAX_MANUAL_UPLOAD_BYTES,
        ingest_manual_platform_backup,
    )

    name = (file.filename or "").strip()
    if not name.lower().endswith(".age"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Se espera un archivo cifrado con extensión .age",
        )

    fd, path_str = tempfile.mkstemp(prefix="msa_pb_up_", suffix=".age", dir="/tmp")
    os.close(fd)
    tmp = Path(path_str)
    total = 0
    try:
        with tmp.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_MANUAL_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="El archivo supera el límite permitido para subida manual (2 GiB).",
                    )
                out.write(chunk)
    except HTTPException:
        tmp.unlink(missing_ok=True)
        raise
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    try:
        result = await ingest_manual_platform_backup(
            db,
            source_file=tmp,
            original_filename=name,
            upload_to_drive=also_upload_to_drive,
        )
    except Exception as exc:  # noqa: BLE001
        tmp.unlink(missing_ok=True)
        await record_audit(
            db,
            action=AuditAction.PLATFORM_BACKUP,
            actor_user_id=current.id,
            actor_label=current.email,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
            success=False,
            metadata={"manual_upload": True, "error": str(exc)[:800]},
        )
        await db.commit()
        return PlatformBackupUploadOut(ok=False, error=str(exc)[:800])

    await record_audit(
        db,
        action=AuditAction.PLATFORM_BACKUP,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        success=bool(result.get("ok")),
        metadata={"manual_upload": True, **{k: v for k, v in result.items() if k != "error"}},
    )
    await db.commit()
    return PlatformBackupUploadOut(
        ok=bool(result.get("ok")),
        local_path=result.get("local_path"),
        drive_file_id=result.get("drive_file_id"),
        error=result.get("error"),
    )


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
