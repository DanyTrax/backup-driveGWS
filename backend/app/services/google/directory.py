"""Admin SDK Directory API wrapper.

Runs the synchronous `googleapiclient` inside a threadpool so it plays nice
with FastAPI's async endpoints and Celery tasks.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.google.credentials import directory_credentials


@dataclass(slots=True)
class WorkspaceUser:
    id: str
    primary_email: str
    full_name: str | None
    given_name: str | None
    family_name: str | None
    suspended: bool
    archived: bool
    is_admin: bool
    org_unit_path: str | None
    raw: dict[str, Any]


def _to_user(row: dict[str, Any]) -> WorkspaceUser:
    name = row.get("name", {}) or {}
    return WorkspaceUser(
        id=str(row.get("id", "")),
        primary_email=str(row.get("primaryEmail", "")).lower(),
        full_name=name.get("fullName"),
        given_name=name.get("givenName"),
        family_name=name.get("familyName"),
        suspended=bool(row.get("suspended", False)),
        archived=bool(row.get("archived", False)),
        is_admin=bool(row.get("isAdmin", False)),
        org_unit_path=row.get("orgUnitPath"),
        raw=row,
    )


async def _build_service(db: AsyncSession):
    creds = await directory_credentials(db)
    return await asyncio.to_thread(
        lambda: build("admin", "directory_v1", credentials=creds, cache_discovery=False)
    )


async def list_users(db: AsyncSession, customer: str = "my_customer") -> list[WorkspaceUser]:
    service = await _build_service(db)

    def _fetch() -> list[WorkspaceUser]:
        users: list[WorkspaceUser] = []
        token: str | None = None
        while True:
            resp = (
                service.users()
                .list(
                    customer=customer,
                    maxResults=500,
                    orderBy="email",
                    pageToken=token,
                    projection="full",
                    viewType="admin_view",
                )
                .execute()
            )
            for u in resp.get("users", []) or []:
                users.append(_to_user(u))
            token = resp.get("nextPageToken")
            if not token:
                break
        return users

    return await asyncio.to_thread(_fetch)


async def check_connection(db: AsyncSession) -> dict[str, Any]:
    """Validate SA + DWD + Admin email: list first page and return stats."""
    try:
        service = await _build_service(db)
        resp = await asyncio.to_thread(
            lambda: service.users()
            .list(customer="my_customer", maxResults=1, projection="basic")
            .execute()
        )
    except HttpError as exc:
        return {"ok": False, "error": f"http_{exc.resp.status}", "detail": str(exc)}
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": "exception", "detail": str(exc)}
    return {"ok": True, "sample_count": len(resp.get("users", []) or [])}
