"""Mantenimiento Docker del host y despliegue de la pila (opcional, super admin)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

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
    vault_item_count_publish_failure,
    vault_item_count_publish_running,
    vault_item_count_publish_success,
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
    """Estado del último conteo (Redis): visible en Mantenimiento; el job sigue en Celery aunque cambies de pestaña."""
    raw = await vault_item_count_read_session()
    if not raw:
        return VaultSharedDriveItemCountSessionOut(state="idle")
    st = raw.get("state")
    if isinstance(st, str):
        st = st.strip().lower()

    corrupt_msg = (
        "Redis devolvió una sesión incompleta (sin id de tarea o sin datos coherentes). "
        "Ejecutá de nuevo el conteo o borrá la clave host_ops:vault_shared_drive_item_count:status en Redis."
    )

    tid_cell = raw.get("task_id")
    tid_s = str(tid_cell).strip() if tid_cell else ""

    # Compat: encolado en broker — solo «en curso» si hay task_id; si no, Redis está corrupto.
    if st in ("pending", "queued", "received", "retry"):
        if not tid_s:
            return VaultSharedDriveItemCountSessionOut(state="failure", error=corrupt_msg)
        st = "running"

    if st not in ("running", "success", "failure"):
        return VaultSharedDriveItemCountSessionOut(state="idle")

    if st == "running" and not tid_s:
        return VaultSharedDriveItemCountSessionOut(state="failure", error=corrupt_msg)

    def _opt_int(val: object) -> int | None:
        if val is None:
            return None
        try:
            return int(val)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

    def _session_body_from_raw(state_ok: str) -> VaultSharedDriveItemCountSessionOut:
        res = raw.get("result")
        parsed_result_inner = None
        result_parse_error_inner = None
        if state_ok == "success":
            if isinstance(res, dict):
                try:
                    parsed_result_inner = VaultSharedDriveItemCountOut.model_validate(res)
                except ValidationError:
                    result_parse_error_inner = "resultado_almacenado_invalido"
            elif res is not None:
                result_parse_error_inner = "resultado_almacenado_invalido"
        err_raw = raw.get("error")
        err_str = str(err_raw).strip() if err_raw is not None and str(err_raw).strip() else None
        if state_ok == "failure" and not err_str:
            err_str = (
                "El job de conteo terminó con error (sin detalle en Redis). "
                "Reejecutá el conteo o revisá logs del worker."
            )
        return VaultSharedDriveItemCountSessionOut(
            state=state_ok,  # type: ignore[arg-type]
            task_id=tid_s or (str(raw["task_id"]) if raw.get("task_id") else None),
            started_at=str(raw["started_at"]) if raw.get("started_at") else None,
            finished_at=str(raw["finished_at"]) if raw.get("finished_at") else None,
            result=parsed_result_inner,
            error=err_str,
            progress_items=_opt_int(raw.get("progress_items")),
            pages_fetched=_opt_int(raw.get("pages_fetched")),
            progress_updated_at=str(raw["progress_updated_at"]) if raw.get("progress_updated_at") else None,
            result_parse_error=result_parse_error_inner,
        )

    if st == "running":
        from celery.result import AsyncResult

        from app.workers.celery_app import celery_app

        ar = AsyncResult(tid_s, app=celery_app)

        pages_n = _opt_int(raw.get("pages_fetched")) or 0

        # Si Redis ya tiene páginas contadas, Celery puede seguir en PENDING (típico sin task_track_started
        # o entre páginas). No interpretar eso como «nunca la tomó el worker».
        # Ventana amplia: entre páginas la API de Drive puede tardar sin actualizar progress_updated_at.
        pua = raw.get("progress_updated_at")
        recent_progress = False
        if pua:
            try:
                pudt = datetime.fromisoformat(str(pua).replace("Z", "+00:00"))
                if pudt.tzinfo is None:
                    pudt = pudt.replace(tzinfo=UTC)
                recent_progress = datetime.now(UTC) - pudt <= timedelta(minutes=45)
            except (ValueError, TypeError):
                pass

        if ar.ready():
            if ar.successful() and isinstance(ar.result, dict):
                try:
                    parsed_live = VaultSharedDriveItemCountOut.model_validate(ar.result)
                except ValidationError:
                    await vault_item_count_publish_failure(tid_s, "invalid_task_result")
                    return VaultSharedDriveItemCountSessionOut(
                        state="failure",
                        task_id=tid_s,
                        started_at=str(raw["started_at"]) if raw.get("started_at") else None,
                        finished_at=None,
                        result=None,
                        error="invalid_task_result",
                    )
                await vault_item_count_publish_success(tid_s, ar.result)
                return VaultSharedDriveItemCountSessionOut(
                    state="success",
                    task_id=tid_s,
                    started_at=str(raw["started_at"]) if raw.get("started_at") else None,
                    finished_at=None,
                    result=parsed_live,
                    error=None,
                    progress_items=None,
                    pages_fetched=None,
                    progress_updated_at=None,
                    result_parse_error=None,
                )
            err = (str(ar.info) if ar.info is not None else "").strip() or "task_failed"
            if ar.state == "REVOKED":
                err = "task_revoked"
            await vault_item_count_publish_failure(tid_s, err[:4000])
            return VaultSharedDriveItemCountSessionOut(
                state="failure",
                task_id=tid_s,
                started_at=str(raw["started_at"]) if raw.get("started_at") else None,
                finished_at=None,
                result=None,
                error=err[:4000],
            )

        sa = raw.get("started_at")
        try:
            if sa and not recent_progress:
                sdt = datetime.fromisoformat(str(sa).replace("Z", "+00:00"))
                if sdt.tzinfo is None:
                    sdt = sdt.replace(tzinfo=UTC)
                age = datetime.now(UTC) - sdt
                if (
                    pages_n == 0
                    and ar.state in ("PENDING", "RECEIVED")
                    and age > timedelta(minutes=50)
                ):
                    stale = (
                        "La tarea lleva más de 50 minutos en cola sin avance en Celery (PENDING/RECEIVED) "
                        "y sin ninguna página contada en Redis. Comprobá el worker y el broker."
                    )
                    await vault_item_count_publish_failure(tid_s, stale)
                    return VaultSharedDriveItemCountSessionOut(
                        state="failure",
                        task_id=tid_s,
                        started_at=str(raw["started_at"]) if raw.get("started_at") else None,
                        finished_at=None,
                        result=None,
                        error=stale,
                    )
                if ar.state in ("STARTED", "RETRY") and age > timedelta(minutes=90):
                    stale = (
                        "La sesión lleva más de 90 minutos sin resultado en Celery (el job tiene límite ~55 min). "
                        "Probable worker caído o Redis desincronizado. Revisá logs del worker y reejecutá el conteo."
                    )
                    await vault_item_count_publish_failure(tid_s, stale)
                    return VaultSharedDriveItemCountSessionOut(
                        state="failure",
                        task_id=tid_s,
                        started_at=str(raw["started_at"]) if raw.get("started_at") else None,
                        finished_at=None,
                        result=None,
                        error=stale,
                    )
        except (ValueError, TypeError):
            pass

    return _session_body_from_raw(st)


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
