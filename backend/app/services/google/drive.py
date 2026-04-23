"""Drive API helpers for vault folder management and connectivity checks."""
from __future__ import annotations

import asyncio
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy.ext.asyncio import AsyncSession

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


async def ensure_account_vault(
    db: AsyncSession,
    *,
    email: str,
    root_folder_id: str,
    drive_id: str | None = None,
) -> dict[str, str]:
    """Create the standard sub-folders for an account: Drive, Gmail-mbox, Reports."""
    top = await ensure_folder(
        db, name=email, parent_id=root_folder_id, drive_id=drive_id
    )
    folders: dict[str, str] = {"root": top["id"]}
    for sub in ("Drive", "Gmail", "Reports"):
        child = await ensure_folder(
            db, name=sub, parent_id=top["id"], drive_id=drive_id
        )
        folders[sub.lower()] = child["id"]
    return folders
