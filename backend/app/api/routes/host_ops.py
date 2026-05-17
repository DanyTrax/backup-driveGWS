"""Mantenimiento Docker del host y despliegue de la pila (opcional, super admin)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_client_ip,
    get_db,
    get_user_agent,
    require_any_permission,
    require_permission,
)
from app.models.enums import AuditAction
from app.models.users import SysUser
from app.schemas.host_ops import (
    DockerPruneRequest,
    HostOpsConfigOut,
    HostOpsScheduleIn,
    StackDeployRequest,
    VaultSharedDriveItemCountJobStartOut,
    VaultSharedDriveItemCountJobStateOut,
    VaultSharedDriveItemCountOut,
    VaultSharedDriveItemCountSessionOut,
)
from app.services.audit_service import record_audit
from app.services.host_ops_service import (
    get_prune_schedule,
    host_ops_public_config,
    run_docker_prune,
    save_prune_schedule,
    stack_deploy_job_status,
    start_stack_deploy_detached,
)
from app.services.vault_shared_drive_item_count_status import (
    vault_item_count_publish_running,
    vault_item_count_read_session,
)
from app.services.settings_service import KEY_VAULT_SHARED_DRIVE_ID, get_value

router = APIRouter(prefix="/admin/host-ops", tags=["admin-host-ops"])


@router.post("/vault-shared-drive-item-count", response_model=VaultSharedDriveItemCountJobStartOut)
async def vault_shared_drive_item_count_start(
    db: AsyncSession = Depends(get_db),
    _: SysUser = Depends(require_any_permission("platform.host_docker", "platform.stack_deploy")),
) -> VaultSharedDriveItemCountJobStartOut:
    """Encola conteo en Celery (la unidad grande supera timeouts de nginx/proxy si se hace en HTTP sync)."""
    from app.workers.tasks.maintenance import vault_shared_drive_item_count as count_task

    drive_id = (await get_value(db, KEY_VAULT_SHARED_DRIVE_ID) or "").strip()
    if not drive_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"error": "missing_shared_drive_id", "message": "Configurá el ID de Shared Drive en el asistente."},
        )

    try:
        async_result = count_task.delay()
    except Exception as exc:  # pragma: no cover — broker caído
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "celery_unavailable", "message": str(exc)},
        ) from exc
    await vault_item_count_publish_running(async_result.id)
    return VaultSharedDriveItemCountJobStartOut(task_id=async_result.id)


@router.get(
    "/vault-shared-drive-item-count/{task_id}",
    response_model=VaultSharedDriveItemCountJobStateOut,
)
async def vault_shared_drive_item_count_status(
    task_id: str,
    _: SysUser = Depends(require_any_permission("platform.host_docker", "platform.stack_deploy")),
) -> VaultSharedDriveItemCountJobStateOut:
    from celery.result import AsyncResult

    from app.workers.celery_app import celery_app

    r = AsyncResult(task_id, app=celery_app)
    st = r.state
    if st in ("PENDING", "RECEIVED", "STARTED", "RETRY"):
        return VaultSharedDriveItemCountJobStateOut(
            state="running" if st in ("STARTED", "RETRY") else "pending",
            result=None,
            error=None,
        )
    if st == "SUCCESS":
        raw = r.result
        if not isinstance(raw, dict):
            return VaultSharedDriveItemCountJobStateOut(
                state="failure",
                result=None,
                error="invalid_task_result",
            )
        return VaultSharedDriveItemCountJobStateOut(
            state="success",
            result=VaultSharedDriveItemCountOut.model_validate(raw),
            error=None,
        )
    if st == "FAILURE":
        err = str(r.info) if r.info is not None else "task_failed"
        return VaultSharedDriveItemCountJobStateOut(state="failure", result=None, error=err[:4000])
    if st == "REVOKED":
        return VaultSharedDriveItemCountJobStateOut(state="failure", result=None, error="task_revoked")
    return VaultSharedDriveItemCountJobStateOut(state="failure", result=None, error=f"unknown_state_{st}")


@router.get("/vault-shared-drive-item-count/session", response_model=VaultSharedDriveItemCountSessionOut)
async def vault_shared_drive_item_count_session_read(
    _: SysUser = Depends(require_any_permission("platform.host_docker", "platform.stack_deploy")),
) -> VaultSharedDriveItemCountSessionOut:
    """Estado del último conteo (Redis): sirve para ver progreso o total desde Logs u otra vista."""
    raw = await vault_item_count_read_session()
    if not raw:
        return VaultSharedDriveItemCountSessionOut(state="idle")
    st = raw.get("state")
    if isinstance(st, str):
        st = st.strip().lower()
    # Compat: estados tipo broker/Celery antes de que el worker escriba "running"
    if st in ("pending", "queued", "received", "retry"):
        st = "running"
    if st not in ("running", "success", "failure"):
        return VaultSharedDriveItemCountSessionOut(state="idle")
    res = raw.get("result")

    def _opt_int(val: object) -> int | None:
        if val is None:
            return None
        try:
            return int(val)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

    parsed_result = None
    result_parse_error = None
    if st == "success":
        if isinstance(res, dict):
            try:
                parsed_result = VaultSharedDriveItemCountOut.model_validate(res)
            except ValidationError:
                result_parse_error = "resultado_almacenado_invalido"
        elif res is not None:
            result_parse_error = "resultado_almacenado_invalido"

    return VaultSharedDriveItemCountSessionOut(
        state=st,
        task_id=str(raw["task_id"]) if raw.get("task_id") else None,
        started_at=str(raw["started_at"]) if raw.get("started_at") else None,
        finished_at=str(raw["finished_at"]) if raw.get("finished_at") else None,
        result=parsed_result,
        error=str(raw["error"]) if raw.get("error") else None,
        progress_items=_opt_int(raw.get("progress_items")),
        pages_fetched=_opt_int(raw.get("pages_fetched")),
        progress_updated_at=str(raw["progress_updated_at"]) if raw.get("progress_updated_at") else None,
        result_parse_error=result_parse_error,
    )


@router.get("/config", response_model=HostOpsConfigOut)
async def host_ops_config(
    db: AsyncSession = Depends(get_db),
    _: SysUser = Depends(require_any_permission("platform.host_docker", "platform.stack_deploy")),
) -> HostOpsConfigOut:
    base = host_ops_public_config()
    sched = await get_prune_schedule(db)
    return HostOpsConfigOut(schedule=sched, **base)


@router.post("/docker-prune")
async def docker_prune_now(
    request: Request,
    payload: DockerPruneRequest,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("platform.host_docker")),
) -> dict:
    result = run_docker_prune(payload.preset)
    await record_audit(
        db,
        action=AuditAction.HOST_DOCKER_PRUNE,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        success=bool(result.get("ok")),
        metadata=result,
    )
    await db.commit()
    return result


@router.post("/cleanup-gyb-zip-tmp")
async def cleanup_gyb_zip_tmp_now(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("platform.host_docker")),
) -> dict:
    """Encola limpieza en el worker (no espera resultado: evita cuelgues del API / 502)."""
    from app.workers.tasks.maintenance import cleanup_gyb_zip_tmp as cleanup_task

    try:
        async_result = cleanup_task.delay()
    except Exception as exc:  # pragma: no cover — broker caído, etc.
        await record_audit(
            db,
            action=AuditAction.HOST_TMP_CLEANUP_GYB_ZIP,
            actor_user_id=current.id,
            actor_label=current.email,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
            success=False,
            metadata={"error": str(exc)},
        )
        await db.commit()
        return {"ok": False, "error": str(exc)}

    meta: dict = {"ok": True, "queued": True, "task_id": async_result.id}
    await record_audit(
        db,
        action=AuditAction.HOST_TMP_CLEANUP_GYB_ZIP,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        success=True,
        metadata=meta,
    )
    try:
        await db.commit()
    except DBAPIError:
        await db.rollback()
        await record_audit(
            db,
            action=AuditAction.HOST_DOCKER_PRUNE,
            actor_user_id=current.id,
            actor_label=current.email,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
            success=True,
            metadata={**meta, "note": "gyb_zip_tmp_queued_run_alembic_0016"},
        )
        await db.commit()
    return meta


@router.get("/docker-prune-schedule")
async def docker_prune_schedule_get(
    db: AsyncSession = Depends(get_db),
    _: SysUser = Depends(require_permission("platform.host_docker")),
) -> dict:
    return await get_prune_schedule(db)


@router.put("/docker-prune-schedule")
async def docker_prune_schedule_put(
    payload: HostOpsScheduleIn,
    db: AsyncSession = Depends(get_db),
    _: SysUser = Depends(require_permission("platform.host_docker")),
) -> dict:
    return await save_prune_schedule(db, payload)


@router.post("/stack-deploy")
async def stack_deploy(
    request: Request,
    payload: StackDeployRequest,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("platform.stack_deploy")),
) -> dict:
    """Encola un contenedor efímero; la respuesta llega en segundos aunque ``app`` se reinicie después."""
    result = start_stack_deploy_detached(payload.mode)
    await record_audit(
        db,
        action=AuditAction.STACK_DEPLOY,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        success=bool(result.get("ok")),
        metadata={"mode": payload.mode, **result},
    )
    await db.commit()
    return result


@router.get("/stack-deploy-job/{job_name}")
async def stack_deploy_job(
    job_name: str,
    _: SysUser = Depends(require_permission("platform.stack_deploy")),
) -> dict:
    return stack_deploy_job_status(job_name)
