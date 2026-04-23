"""Build google.auth Credentials from the stored Service Account JSON."""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from google.oauth2 import service_account
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.settings_service import (
    KEY_GOOGLE_DELEGATED_ADMIN,
    KEY_GOOGLE_SA_JSON,
    get_value,
)

DIRECTORY_SCOPES = [
    "https://www.googleapis.com/auth/admin.directory.user.readonly",
    "https://www.googleapis.com/auth/admin.directory.customer.readonly",
]
DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/drive",
]
GMAIL_SEND_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
]
GMAIL_FULL_SCOPES = [
    "https://mail.google.com/",
]


class GoogleNotConfigured(RuntimeError):
    pass


async def load_sa_info(db: AsyncSession) -> dict[str, Any]:
    raw = await get_value(db, KEY_GOOGLE_SA_JSON)
    if not raw:
        raise GoogleNotConfigured("service_account_json_missing")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GoogleNotConfigured(f"invalid_service_account_json: {exc}") from exc
    if data.get("type") != "service_account":
        raise GoogleNotConfigured("not_a_service_account")
    return data


async def get_admin_email(db: AsyncSession) -> str:
    email = await get_value(db, KEY_GOOGLE_DELEGATED_ADMIN)
    if not email:
        raise GoogleNotConfigured("delegated_admin_email_missing")
    return email


def _build_credentials(
    sa_info: dict[str, Any], scopes: list[str], subject: str | None
) -> service_account.Credentials:
    creds = service_account.Credentials.from_service_account_info(sa_info, scopes=scopes)
    if subject:
        creds = creds.with_subject(subject)
    return creds


async def directory_credentials(db: AsyncSession) -> service_account.Credentials:
    sa_info = await load_sa_info(db)
    admin = await get_admin_email(db)
    return _build_credentials(sa_info, DIRECTORY_SCOPES, admin)


async def drive_credentials(db: AsyncSession, subject: str | None = None) -> service_account.Credentials:
    sa_info = await load_sa_info(db)
    if subject is None:
        subject = await get_admin_email(db)
    return _build_credentials(sa_info, DRIVE_SCOPES, subject)


async def gmail_send_credentials(db: AsyncSession, subject: str) -> service_account.Credentials:
    sa_info = await load_sa_info(db)
    return _build_credentials(sa_info, GMAIL_SEND_SCOPES, subject)


@lru_cache(maxsize=1)
def _required_oauth_scopes_text() -> str:
    scopes = set(DIRECTORY_SCOPES + DRIVE_SCOPES + GMAIL_FULL_SCOPES + GMAIL_SEND_SCOPES)
    return ",".join(sorted(scopes))


def dwd_client_id(sa_info: dict[str, Any]) -> str:
    return str(sa_info.get("client_id", ""))
