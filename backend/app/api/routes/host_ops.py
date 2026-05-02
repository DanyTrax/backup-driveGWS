"""Mantenimiento Docker del host y despliegue de la pila (opcional, super admin)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
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

router = APIRouter(prefix="/admin/host-ops", tags=["admin-host-ops"])


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
