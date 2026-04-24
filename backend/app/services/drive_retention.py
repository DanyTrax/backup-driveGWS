"""Retención de snapshots fechados en el vault de Drive (no aplica a Maildir/Gmail)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.drive_snapshot_retention_plan import folder_ids_to_prune
from app.services.google.drive import delete_drive_file, get_folder_by_name, list_child_folders
from app.services.settings_service import KEY_VAULT_SHARED_DRIVE_ID, get_value

if TYPE_CHECKING:
    from app.models.accounts import GwAccount
    from app.models.tasks import BackupTask


async def prune_after_drive_backup(
    db: AsyncSession,
    *,
    task: BackupTask,
    account: GwAccount,
) -> int:
    """Elimina las carpetas de ejecución más antiguas bajo MSA_Runs/, dejando las N más recientes.

    ``retention_policy_json.keep_drive_snapshots`` = N (entero > 0). N=0 o ausente = sin poda.
    Solo actúa si la tarea usa ``filters_json.drive_layout == \"dated_run\"``.
    """
    policy = task.retention_policy_json or {}
    keep = int(policy.get("keep_drive_snapshots") or 0)
    if keep <= 0:
        return 0

    filters = task.filters_json or {}
    if filters.get("drive_layout") != "dated_run":
        return 0

    vault_id = account.drive_vault_folder_id
    if not vault_id:
        return 0

    drive_id = await get_value(db, KEY_VAULT_SHARED_DRIVE_ID)
    prefix = str(filters.get("dated_run_prefix", "MSA_Runs")).strip("/") or "MSA_Runs"

    runs = await get_folder_by_name(db, name=prefix, parent_id=vault_id, drive_id=drive_id)
    if not runs:
        return 0

    children = await list_child_folders(db, parent_id=runs["id"], drive_id=drive_id)
    to_remove = folder_ids_to_prune(children, keep=keep)
    for file_id in to_remove:
        await delete_drive_file(db, file_id=file_id)
    return len(to_remove)
