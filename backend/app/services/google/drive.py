"""Drive API helpers for vault folder management and connectivity checks."""
from __future__ import annotations

import asyncio
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.computers_folder_names import (
    computers_name_priority,
    fold_display_name,
    is_computers_backup_root_folder_name,
)
from app.services.google.credentials import drive_credentials


async def build_drive_service(db: AsyncSession, subject: str | None = None):
    creds = await drive_credentials(db, subject)
    return await asyncio.to_thread(
        lambda: build("drive", "v3", credentials=creds, cache_discovery=False)
    )


# legacy private alias kept for callers still using the underscore name
_build_service = build_drive_service


async def list_shared_drives(db: AsyncSession) -> list[dict[str, Any]]:
    service = await _build_service(db)

    def _fetch() -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        token: str | None = None
        while True:
            resp = service.drives().list(pageSize=100, pageToken=token).execute()
            out.extend(resp.get("drives", []) or [])
            token = resp.get("nextPageToken")
            if not token:
                break
        return out

    return await asyncio.to_thread(_fetch)


async def get_drive_about(db: AsyncSession) -> dict[str, Any]:
    service = await _build_service(db)
    return await asyncio.to_thread(
        lambda: service.about().get(fields="user,storageQuota").execute()
    )


async def check_shared_drive(db: AsyncSession, drive_id: str) -> dict[str, Any]:
    try:
        service = await _build_service(db)
        resp = await asyncio.to_thread(
            lambda: service.drives()
            .get(driveId=drive_id, fields="id,name,capabilities")
            .execute()
        )
        return {"ok": True, "drive": resp}
    except HttpError as exc:
        return {"ok": False, "error": f"http_{exc.resp.status}", "detail": str(exc)}
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": "exception", "detail": str(exc)}


async def ensure_folder(
    db: AsyncSession,
    *,
    name: str,
    parent_id: str,
    drive_id: str | None = None,
) -> dict[str, Any]:
    """Return a folder with `name` under `parent_id`, creating it if absent."""
    service = await _build_service(db)

    def _op() -> dict[str, Any]:
        safe_name = name.replace("'", "\\'")
        q = (
            f"name = '{safe_name}' and "
            f"'{parent_id}' in parents and "
            "mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        )
        kwargs: dict[str, Any] = {
            "q": q,
            "fields": "files(id,name,parents)",
            "pageSize": 1,
            "supportsAllDrives": True,
            "includeItemsFromAllDrives": True,
        }
        if drive_id:
            kwargs["corpora"] = "drive"
            kwargs["driveId"] = drive_id
        resp = service.files().list(**kwargs).execute()
        files = resp.get("files", []) or []
        if files:
            return files[0]
        body = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        return (
            service.files()
            .create(body=body, fields="id,name,parents", supportsAllDrives=True)
            .execute()
        )

    return await asyncio.to_thread(_op)


async def get_folder_by_name(
    db: AsyncSession,
    *,
    name: str,
    parent_id: str,
    drive_id: str | None = None,
) -> dict[str, Any] | None:
    """Return first non-trashed folder named `name` under `parent_id`, or None."""
    service = await _build_service(db)

    def _op() -> dict[str, Any] | None:
        safe_name = name.replace("'", "\\'")
        q = (
            f"name = '{safe_name}' and "
            f"'{parent_id}' in parents and "
            "mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        )
        kwargs: dict[str, Any] = {
            "q": q,
            "fields": "files(id,name)",
            "pageSize": 1,
            "supportsAllDrives": True,
            "includeItemsFromAllDrives": True,
        }
        if drive_id:
            kwargs["corpora"] = "drive"
            kwargs["driveId"] = drive_id
        resp = service.files().list(**kwargs).execute()
        files = resp.get("files", []) or []
        return files[0] if files else None

    return await asyncio.to_thread(_op)


async def list_child_folders(
    db: AsyncSession,
    *,
    parent_id: str,
    drive_id: str | None = None,
    impersonate_user: str | None = None,
) -> list[dict[str, Any]]:
    """Immediate subfolders of parent_id (folders only).

    Con ``impersonate_user`` se usa Domain-Wide Delegation hacia esa cuenta (p. ej. listar la raíz
    de «Mi unidad»). Sin él se usa la identidad admin de la service account (típico del vault).
    """
    service = await build_drive_service(db, impersonate_user)

    def _op() -> list[dict[str, Any]]:
        q = (
            f"'{parent_id}' in parents and "
            "mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        )
        kwargs: dict[str, Any] = {
            "q": q,
            "fields": "files(id,name)",
            "pageSize": 100,
            "supportsAllDrives": True,
            "includeItemsFromAllDrives": True,
        }
        if drive_id:
            kwargs["corpora"] = "drive"
            kwargs["driveId"] = drive_id
        out: list[dict[str, Any]] = []
        token: str | None = None
        while True:
            req = {**kwargs}
            if token:
                req["pageToken"] = token
            resp = service.files().list(**req).execute()
            out.extend(resp.get("files", []) or [])
            token = resp.get("nextPageToken")
            if not token:
                break
        return out

    return await asyncio.to_thread(_op)


async def find_computers_backup_folder_id(
    db: AsyncSession,
    *,
    subject: str,
) -> tuple[str | None, str | None, str]:
    """Localiza carpeta de respaldos «Computadoras / Computers» en la raíz de Mi unidad.

    Devuelve ``(folder_id, nombre_elegido, texto_explicativo)``. Si no hay carpeta reconocible,
    ``folder_id`` y ``nombre_elegido`` son ``None`` y ``texto_explicativo`` resume el hallazgo
    para informes (la corrida puede finalizar en éxito sin copiar nada).
    """
    try:
        children = await list_child_folders(
            db,
            parent_id="root",
            drive_id=None,
            impersonate_user=subject,
        )
    except Exception as exc:  # pragma: no cover
        return None, None, f"No se pudo listar la raíz de Drive del usuario: {exc}"

    candidates = [c for c in children if is_computers_backup_root_folder_name(str(c.get("name") or ""))]
    if not candidates:
        names_list = sorted({str(c.get("name") or "?") for c in children})
        sample = ", ".join(names_list[:25])
        more = f" (+{len(names_list) - 25} nombres más)" if len(names_list) > 25 else ""
        return (
            None,
            None,
            "No se encontró carpeta de respaldos de equipos (Google Drive for desktop / «Computadoras»). "
            "Se revisaron las carpetas en la raíz de «Mi unidad» bajo nombres habituales "
            "(«Computadoras», «Computers», «Otras computadoras», etc.) sin coincidencias. "
            f"Carpetas en raíz ({len(names_list)}): {sample}{more}. "
            "Si no usás la copia de carpetas del PC hacia Drive, este resultado es esperado.",
        )

    candidates.sort(
        key=lambda c: (
            computers_name_priority(str(c.get("name") or "")),
            fold_display_name(str(c.get("name") or "")),
        )
    )
    chosen = candidates[0]
    fid = str(chosen["id"])
    fname = str(chosen.get("name") or "")
    if len(candidates) > 1:
        alt = ", ".join(f"«{c.get('name')}»" for c in candidates[1:4])
        suffix = f" Varias coincidencias; se usa «{fname}». Otras: {alt}."
        if len(candidates) > 4:
            suffix += f" (+{len(candidates) - 4})"
    else:
        suffix = ""
    return fid, fname, f"Carpeta de respaldos de equipos detectada: «{fname}».{suffix}"


def vault_account_root_metadata_ok(
    meta: dict[str, Any] | None,
    *,
    root_folder_id: str,
) -> bool:
    """True si ``meta`` es una carpeta no eliminada y sigue colgando del vault raíz configurado."""
    if not meta or meta.get("trashed"):
        return False
    if meta.get("mimeType") != "application/vnd.google-apps.folder":
        return False
    parents = meta.get("parents") or []
    return root_folder_id in parents


async def get_drive_folder_metadata(
    db: AsyncSession,
    *,
    file_id: str,
) -> dict[str, Any] | None:
    """Metadatos de carpeta/archivo, o None si no existe (404)."""
    service = await _build_service(db)

    def _op() -> dict[str, Any] | None:
        try:
            return (
                service.files()
                .get(
                    fileId=file_id,
                    fields="id,name,mimeType,trashed,parents",
                    supportsAllDrives=True,
                )
                .execute()
            )
        except HttpError as exc:
            if exc.resp.status == 404:
                return None
            raise

    return await asyncio.to_thread(_op)


async def delete_drive_file(db: AsyncSession, *, file_id: str) -> None:
    """Permanently remove a Drive file/folder (vault cleanup)."""
    service = await _build_service(db)

    def _op() -> None:
        service.files().delete(fileId=file_id, supportsAllDrives=True).execute()

    await asyncio.to_thread(_op)


async def ensure_account_vault(
    db: AsyncSession,
    *,
    email: str,
    root_folder_id: str,
    drive_id: str | None = None,
    preferred_account_folder_id: str | None = None,
) -> dict[str, str]:
    """Crea la jerarquía estándar bajo el vault de la cuenta (al activar backup).

    Si ``preferred_account_folder_id`` sigue siendo una carpeta válida bajo el vault raíz
    (reactivación tras deshabilitar backup), se reutiliza y no se crea otra carpeta con el mismo email.

    Estructura (alineada a ``vault_layout``)::

        <email>/
          1-GMAIL/          # push GYB → 1-GMAIL/gyb_mbox en backups
          2-DRIVE/        # rclone Mi unidad → 2-DRIVE/...
          3-REPORTS/
            reports/      # informes / exportaciones
            logs/         # logs de ejecución u otros

    Devuelve ids útiles: ``root`` (carpeta del email, la que se guarda en ``drive_vault_folder_id``),
    más claves legadas ``gmail`` / ``drive`` / ``reports`` y subcarpetas bajo reports.
    """
    from app.services import vault_layout as vl

    top_id: str | None = None
    pref = (preferred_account_folder_id or "").strip()
    if pref:
        meta = await get_drive_folder_metadata(db, file_id=pref)
        if vault_account_root_metadata_ok(meta, root_folder_id=root_folder_id):
            top_id = str(meta["id"])

    if top_id is None:
        top = await ensure_folder(
            db, name=email, parent_id=root_folder_id, drive_id=drive_id
        )
        top_id = str(top["id"])

    folders: dict[str, str] = {"root": top_id}

    gmail_f = await ensure_folder(
        db, name=vl.VAULT_DIR_GMAIL, parent_id=top_id, drive_id=drive_id
    )
    drive_f = await ensure_folder(
        db, name=vl.VAULT_DIR_DRIVE, parent_id=top_id, drive_id=drive_id
    )
    reports_root = await ensure_folder(
        db, name=vl.VAULT_DIR_REPORTS, parent_id=top_id, drive_id=drive_id
    )
    reports_sub = await ensure_folder(
        db,
        name=vl.VAULT_REPORTS_SUBDIR_REPORTS,
        parent_id=reports_root["id"],
        drive_id=drive_id,
    )
    logs_sub = await ensure_folder(
        db,
        name=vl.VAULT_REPORTS_SUBDIR_LOGS,
        parent_id=reports_root["id"],
        drive_id=drive_id,
    )

    folders["gmail"] = gmail_f["id"]
    folders["drive"] = drive_f["id"]
    folders["reports"] = reports_root["id"]
    folders["reports_exports"] = reports_sub["id"]
    folders["reports_logs"] = logs_sub["id"]
    return folders
