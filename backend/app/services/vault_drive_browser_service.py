"""Listado y búsqueda acotada en el árbol de la bóveda por cuenta (Drive API)."""
from __future__ import annotations

import asyncio
import re
from collections import deque
from typing import Any

from googleapiclient.errors import HttpError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.google.drive import id_is_under_vault_folder, list_drive_folder_children_page

_BAD_NAME_QUERY = re.compile(r"['\\]")

MIME_FOLDER = "application/vnd.google-apps.folder"
MAX_SUBTREE_FOLDERS = 450
MAX_SUBTREE_MATCHES = 120


def _item_to_row(raw: dict[str, Any]) -> dict[str, Any]:
    mid = str(raw.get("id") or "")
    mime = str(raw.get("mimeType") or "")
    shortcut = raw.get("shortcutDetails") or {}
    if isinstance(shortcut, dict) and shortcut.get("targetMimeType"):
        mime = str(shortcut.get("targetMimeType") or mime)
    size_raw = raw.get("size")
    size: int | None
    try:
        size = int(size_raw) if size_raw is not None else None
    except (TypeError, ValueError):
        size = None
    return {
        "id": mid,
        "name": str(raw.get("name") or ""),
        "mime_type": mime,
        "is_folder": mime == MIME_FOLDER,
        "size": size,
        "modified_time": raw.get("modifiedTime"),
        "web_view_link": raw.get("webViewLink"),
    }


async def list_vault_page(
    db: AsyncSession,
    *,
    vault_root_id: str,
    parent_folder_id: str | None,
    page_token: str | None,
    page_size: int,
) -> dict[str, Any]:
    parent = (parent_folder_id or "").strip() or vault_root_id
    if parent != vault_root_id:
        if not await id_is_under_vault_folder(db, vault_root_id=vault_root_id, item_id=parent):
            return {"items": [], "next_page_token": None, "error": "parent_not_in_vault"}
    try:
        page = await list_drive_folder_children_page(
            db,
            parent_folder_id=parent,
            page_token=page_token,
            page_size=page_size,
        )
    except HttpError as exc:
        return {
            "items": [],
            "next_page_token": None,
            "error": f"drive_http_{exc.resp.status}",
        }
    files = page.get("files") or []
    return {
        "items": [_item_to_row(f) for f in files],
        "next_page_token": page.get("nextPageToken"),
        "error": None,
    }


async def search_vault_subtree(
    db: AsyncSession,
    *,
    vault_root_id: str,
    name_substring: str,
) -> dict[str, Any]:
    q = (name_substring or "").strip()
    if len(q) < 2:
        return {"items": [], "truncated": False, "error": "query_too_short"}
    if _BAD_NAME_QUERY.search(q):
        return {"items": [], "truncated": False, "error": "invalid_query"}
    q_lower = q.lower()
    matches: list[dict[str, Any]] = []
    visited: set[str] = set()
    queue: deque[str] = deque([vault_root_id])
    folder_count = 0

    while queue and len(matches) < MAX_SUBTREE_MATCHES and folder_count < MAX_SUBTREE_FOLDERS:
        folder_id = queue.popleft()
        if folder_id in visited:
            continue
        visited.add(folder_id)
        folder_count += 1
        token: str | None = None
        try:
            while True:
                page = await list_drive_folder_children_page(
                    db, parent_folder_id=folder_id, page_token=token, page_size=100
                )
                for raw in page.get("files") or []:
                    name = str(raw.get("name") or "")
                    mime = str(raw.get("mimeType") or "")
                    if q_lower in name.lower():
                        matches.append(_item_to_row(raw))
                        if len(matches) >= MAX_SUBTREE_MATCHES:
                            break
                    if mime == MIME_FOLDER:
                        fid = str(raw.get("id") or "")
                        if fid and fid not in visited:
                            queue.append(fid)
                if len(matches) >= MAX_SUBTREE_MATCHES:
                    break
                token = page.get("nextPageToken")
                if not token:
                    break
        except HttpError as exc:
            return {
                "items": matches,
                "truncated": True,
                "error": f"drive_http_{exc.resp.status}",
            }
        await asyncio.sleep(0)

    truncated = (
        len(matches) >= MAX_SUBTREE_MATCHES
        or folder_count >= MAX_SUBTREE_FOLDERS
        or bool(queue)
    )
    return {"items": matches, "truncated": truncated, "error": None}
