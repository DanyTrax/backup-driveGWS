"""Comprueba acceso efectivo a Drive (DWD + vault) y Gmail (GYB) por cuenta."""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accounts import GwAccount
from app.models.enums import AccountStatus
from app.services import gyb_service, rclone_service
from app.services.maildir_paths import maildir_root_for_account


def _tail(text: str, max_len: int = 1800) -> str:
    t = (text or "").strip()
    if len(t) <= max_len:
        return t
    return "…" + t[-max_len:]


def _maildir_layout_ok(root: Path) -> bool:
    if not root.is_dir():
        return False
    return all((root / sub).is_dir() for sub in ("cur", "new", "tmp"))


async def verify_account_access(db: AsyncSession, account: GwAccount) -> dict[str, object]:
    """Ejecuta comprobaciones reales (rclone + GYB), no solo flags en BD."""
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

    if account.workspace_status == AccountStatus.DELETED_IN_WORKSPACE.value:
        msg = "cuenta_eliminada_en_workspace"
        result["drive_detail"] = msg
        result["gmail_detail"] = msg
        root = maildir_root_for_account(account)
        result["maildir_path"] = str(root)
        result["maildir_layout_ok"] = _maildir_layout_ok(root)
        return result

    # --- Drive: delegación a Mi unidad + carpeta vault si existe
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
        else:
            result["drive_ok"] = True
            result["drive_detail"] = "delegacion_ok: se leyó cuota de Mi unidad del usuario"
            vault_id = (account.drive_vault_folder_id or "").strip()
            if vault_id:
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
                else:
                    result["drive_detail"] = "ok: delegación + carpeta vault listable"
    except Exception as exc:  # pragma: no cover
        result["drive_ok"] = False
        result["drive_detail"] = f"error_drive: {exc!s}"[:2000]

    # --- Gmail: GYB estimate (API Gmail con la misma SA que el backup)
    work = Path(f"/tmp/gyb_access_check_{uuid.uuid4().hex}")
    try:
        work.mkdir(parents=True, exist_ok=True)
        async with gyb_service.prepare_gyb_workspace(
            db, account_email=email, local_folder=str(work)
        ) as workspace:
            argv = gyb_service.build_gyb_argv(workspace, email=email, action="estimate")
            rc, text = await gyb_service.run_gyb(argv, timeout=300)
        if rc != 0:
            result["gmail_detail"] = f"gyb_estimate_fallo (rc={rc}): {_tail(text)}"
        else:
            result["gmail_ok"] = True
            result["gmail_detail"] = f"gyb_ok: {_tail(text, 800)}"
    except Exception as exc:  # pragma: no cover
        result["gmail_detail"] = f"error_gmail: {exc!s}"[:2000]
    finally:
        shutil.rmtree(work, ignore_errors=True)

    root = maildir_root_for_account(account)
    result["maildir_path"] = str(root)
    result["maildir_layout_ok"] = _maildir_layout_ok(root)

    return result
