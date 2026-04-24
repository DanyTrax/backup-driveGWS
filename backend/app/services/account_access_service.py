"""Comprueba acceso efectivo a Drive (DWD + vault) y Gmail (GYB) por cuenta."""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accounts import GwAccount
from app.models.enums import AccountStatus
from app.services import gyb_service, rclone_service
from app.services.maildir_paths import maildir_root_for_account
from app.services.progress_bus import publish


def _tail(text: str, max_len: int = 1800) -> str:
    t = (text or "").strip()
    if len(t) <= max_len:
        return t
    return "…" + t[-max_len:]


def _maildir_layout_ok(root: Path) -> bool:
    if not root.is_dir():
        return False
    return all((root / sub).is_dir() for sub in ("cur", "new", "tmp"))


async def _emit(progress_id: str | None, **payload: Any) -> None:
    if not progress_id:
        return
    await publish(progress_id, {"stage": "verify_access", **payload})


async def verify_account_access(
    db: AsyncSession,
    account: GwAccount,
    *,
    progress_id: str | None = None,
) -> dict[str, object]:
    """Ejecuta comprobaciones reales (rclone + GYB), no solo flags en BD.

    Si ``progress_id`` está definido, publica eventos en Redis (mismo canal que el WS
    ``/api/backup/ws/progress/{id}``) con ``stage=verify_access`` y fases sucesivas.
    """
    email = account.email
    result: dict[str, object] = {
        "account_id": str(account.id),
        "email": email,
        "drive_ok": False,
        "drive_detail": None,
        "gmail_ok": False,
        "gmail_detail": None,
        "maildir_path": None,
        "maildir_layout_ok": False,
    }

    await _emit(
        progress_id,
        phase="started",
        progress_pct=3,
        message="Iniciando comprobación…",
    )

    if account.workspace_status == AccountStatus.DELETED_IN_WORKSPACE.value:
        msg = "cuenta_eliminada_en_workspace"
        result["drive_detail"] = msg
        result["gmail_detail"] = msg
        root = maildir_root_for_account(account)
        result["maildir_path"] = str(root)
        result["maildir_layout_ok"] = _maildir_layout_ok(root)
        await _emit(
            progress_id,
            phase="complete",
            progress_pct=100,
            message="Cuenta eliminada en Workspace.",
            result=result,
        )
        return result

    # --- Drive: delegación a Mi unidad + carpeta vault si existe
    await _emit(
        progress_id,
        phase="drive_delegation",
        progress_pct=8,
        message="Delegación a Google Drive (Mi unidad del usuario)…",
    )
    try:
        async with rclone_service.build_rclone_source_only_config(
            db, impersonate_email=email
        ) as cfg:
            rc, text = await rclone_service.run_rclone(
                ["about", cfg.remote_source, "--config", cfg.config_path],
                timeout=90,
            )
        if rc != 0:
            result["drive_detail"] = f"delegacion_drive_fallo (rc={rc}): {_tail(text)}"
            await _emit(
                progress_id,
                phase="drive_delegation_done",
                progress_pct=25,
                message="Fallo al leer Mi unidad.",
                drive_ok=False,
            )
        else:
            result["drive_ok"] = True
            result["drive_detail"] = "delegacion_ok: se leyó cuota de Mi unidad del usuario"
            await _emit(
                progress_id,
                phase="drive_delegation_done",
                progress_pct=28,
                message="Mi unidad accesible.",
                drive_ok=True,
            )
            vault_id = (account.drive_vault_folder_id or "").strip()
            if vault_id:
                await _emit(
                    progress_id,
                    phase="drive_vault",
                    progress_pct=30,
                    message="Listando carpeta vault de backup…",
                )
                async with rclone_service.build_rclone_config(
                    db,
                    impersonate_email=email,
                    vault_folder_id=vault_id,
                ) as cfg2:
                    rc2, text2 = await rclone_service.run_rclone(
                        [
                            "lsf",
                            cfg2.remote_dest,
                            "--config",
                            cfg2.config_path,
                            "--max-depth",
                            "1",
                        ],
                        timeout=90,
                    )
                if rc2 != 0:
                    result["drive_ok"] = False
                    result["drive_detail"] = (
                        f"vault_no_accesible (rc={rc2}): {_tail(text2)}"
                    )
                    await _emit(
                        progress_id,
                        phase="drive_vault_done",
                        progress_pct=35,
                        message="No se pudo listar el vault.",
                        drive_ok=False,
                    )
                else:
                    result["drive_detail"] = "ok: delegación + carpeta vault listable"
                    await _emit(
                        progress_id,
                        phase="drive_vault_done",
                        progress_pct=36,
                        message="Vault accesible.",
                        drive_ok=True,
                    )
    except Exception as exc:  # pragma: no cover
        result["drive_ok"] = False
        result["drive_detail"] = f"error_drive: {exc!s}"[:2000]
        await _emit(
            progress_id,
            phase="drive_error",
            progress_pct=30,
            message=str(exc)[:500],
            drive_ok=False,
        )

    # --- Gmail: GYB estimate (API Gmail con la misma SA que el backup)
    await _emit(
        progress_id,
        phase="gmail_estimate",
        progress_pct=40,
        message="Estimando buzón Gmail (GYB, puede tardar varios minutos)…",
    )
    work = Path(f"/tmp/gyb_access_check_{uuid.uuid4().hex}")
    gyb_line_count = 0

    async def _gyb_activity(line: str) -> None:
        nonlocal gyb_line_count
        gyb_line_count += 1
        pct = min(88, 42 + min(gyb_line_count, 23) * 2)
        await _emit(
            progress_id,
            phase="gmail_estimate",
            progress_pct=pct,
            message="GYB en ejecución…",
            gmail_activity=line[-280:],
        )

    try:
        work.mkdir(parents=True, exist_ok=True)
        async with gyb_service.prepare_gyb_workspace(
            db, account_email=email, local_folder=str(work)
        ) as workspace:
            argv = gyb_service.build_gyb_argv(workspace, email=email, action="estimate")
            rc, text = await gyb_service.run_gyb(
                argv,
                timeout=300,
                async_on_line=_gyb_activity if progress_id else None,
            )
        if rc != 0:
            result["gmail_detail"] = f"gyb_estimate_fallo (rc={rc}): {_tail(text)}"
            await _emit(
                progress_id,
                phase="gmail_done",
                progress_pct=90,
                message="GYB finalizó con error.",
                gmail_ok=False,
            )
        else:
            result["gmail_ok"] = True
            result["gmail_detail"] = f"gyb_ok: {_tail(text, 800)}"
            await _emit(
                progress_id,
                phase="gmail_done",
                progress_pct=92,
                message="Gmail accesible (estimate OK).",
                gmail_ok=True,
            )
    except Exception as exc:  # pragma: no cover
        result["gmail_detail"] = f"error_gmail: {exc!s}"[:2000]
        await _emit(
            progress_id,
            phase="gmail_error",
            progress_pct=85,
            message=str(exc)[:500],
            gmail_ok=False,
        )
    finally:
        shutil.rmtree(work, ignore_errors=True)

    await _emit(
        progress_id,
        phase="maildir",
        progress_pct=96,
        message="Comprobando Maildir en el servidor…",
    )
    root = maildir_root_for_account(account)
    result["maildir_path"] = str(root)
    result["maildir_layout_ok"] = _maildir_layout_ok(root)

    await _emit(
        progress_id,
        phase="complete",
        progress_pct=100,
        message="Comprobación finalizada.",
        result=result,
    )
    return result
