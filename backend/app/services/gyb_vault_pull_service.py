"""Traer export GYB desde la bóveda Drive (1-GMAIL/gyb_mbox) al disco de trabajo local."""
from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accounts import GwAccount
from app.services import rclone_service
from app.services.mail_purge_service import (
    _purge_gyb_workdir_contents,
    gyb_work_root_for_email,
)
from app.services.vault_layout import gmail_vault_rclone_subpath


async def restore_gyb_workdir_from_vault(
    db: AsyncSession,
    *,
    account: GwAccount,
    purge_workdir_first: bool = False,
) -> tuple[int, str, Path]:
    """``rclone copy`` vault → ``/var/msa/work/gmail/<email>/``.

    Con ``purge_workdir_first`` se vacía antes la carpeta local (misma rutina que la purga selectiva GYB).
    Sin ello, la copia es incremental y no borra en local lo que ya no exista en Drive.
    """
    vault_id = (account.drive_vault_folder_id or "").strip()
    if not vault_id:
        raise ValueError("missing_drive_vault_folder_id")
    work_root = gyb_work_root_for_email(account.email)
    if purge_workdir_first:
        await asyncio.to_thread(_purge_gyb_workdir_contents, work_root)
    work_root.mkdir(parents=True, exist_ok=True)
    subpath = gmail_vault_rclone_subpath()
    async with rclone_service.build_rclone_vault_dest_only_config(
        db, vault_folder_id=vault_id
    ) as cfg:
        argv = rclone_service.build_rclone_vault_to_local_argv(
            str(work_root),
            cfg,
            source_subpath=subpath,
        )
        rc, out = await rclone_service.run_rclone(argv, timeout=None)
    return rc, out, work_root
