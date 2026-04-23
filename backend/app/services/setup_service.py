"""Setup-wizard orchestration."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.google.credentials import (
    DIRECTORY_SCOPES,
    DRIVE_SCOPES,
    GMAIL_FULL_SCOPES,
    GMAIL_SEND_SCOPES,
)
from app.services.settings_service import (
    KEY_GOOGLE_DELEGATED_ADMIN,
    KEY_GOOGLE_SA_JSON,
    KEY_NOTIFY_DISCORD_WEBHOOK,
    KEY_NOTIFY_GMAIL_DELEGATED,
    KEY_NOTIFY_GMAIL_FROM,
    KEY_NOTIFY_GMAIL_RECIPIENTS,
    KEY_NOTIFY_TELEGRAM_BOT,
    KEY_NOTIFY_TELEGRAM_CHAT,
    KEY_SETUP_STATE,
    KEY_VAULT_ROOT_FOLDER_ID,
    KEY_VAULT_SHARED_DRIVE_ID,
    get_json,
    get_value,
    set_json,
    set_value,
)

ALL_SCOPES = sorted(set(DIRECTORY_SCOPES + DRIVE_SCOPES + GMAIL_FULL_SCOPES + GMAIL_SEND_SCOPES))

STEPS: tuple[str, ...] = (
    "service_account",
    "delegation_check",
    "vault_drive",
    "vault_root",
    "notifications",
    "completed",
)


async def load_state(db: AsyncSession) -> dict[str, Any]:
    state = await get_json(db, KEY_SETUP_STATE, default={}) or {}
    flags = {step: bool(state.get(step)) for step in STEPS}
    for step in STEPS:
        if not flags[step]:
            current = step
            break
    else:
        current = "completed"
    client_id = None
    sa_raw = await get_value(db, KEY_GOOGLE_SA_JSON)
    if sa_raw:
        try:
            client_id = str(json.loads(sa_raw).get("client_id"))
        except Exception:
            client_id = None
    return {
        "completed": flags.get("completed", False),
        "current_step": current,
        "steps": flags,
        "google_client_id": client_id,
        "required_scopes": ALL_SCOPES,
    }


async def mark_step(db: AsyncSession, step: str, done: bool = True) -> None:
    state = await get_json(db, KEY_SETUP_STATE, default={}) or {}
    state[step] = done
    await set_json(db, KEY_SETUP_STATE, state, category="setup")


async def store_service_account(
    db: AsyncSession, service_account_json: str, delegated_admin_email: str
) -> dict[str, Any]:
    try:
        data = json.loads(service_account_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid_json: {exc}") from exc
    required = {"type", "client_id", "client_email", "private_key", "token_uri"}
    missing = required - data.keys()
    if missing:
        raise ValueError(f"missing_keys:{sorted(missing)}")
    if data.get("type") != "service_account":
        raise ValueError("not_a_service_account")

    await set_value(
        db,
        KEY_GOOGLE_SA_JSON,
        service_account_json,
        is_secret=True,
        category="google",
        description="Service Account JSON with Domain-Wide Delegation",
    )
    await set_value(
        db,
        KEY_GOOGLE_DELEGATED_ADMIN,
        delegated_admin_email.lower(),
        is_secret=False,
        category="google",
        description="Workspace super-admin impersonated by the SA",
    )
    await mark_step(db, "service_account", True)
    return {
        "client_id": str(data.get("client_id")),
        "client_email": str(data.get("client_email")),
        "required_scopes": ALL_SCOPES,
    }


async def save_shared_drive(db: AsyncSession, drive_id: str) -> None:
    await set_value(db, KEY_VAULT_SHARED_DRIVE_ID, drive_id, category="vault")
    await mark_step(db, "vault_drive", True)


async def save_root_folder(db: AsyncSession, folder_id: str) -> None:
    await set_value(db, KEY_VAULT_ROOT_FOLDER_ID, folder_id, category="vault")
    await mark_step(db, "vault_root", True)


async def save_notifications(db: AsyncSession, payload: dict[str, Any]) -> None:
    mapping = [
        ("telegram_bot_token", KEY_NOTIFY_TELEGRAM_BOT, True),
        ("telegram_chat_id", KEY_NOTIFY_TELEGRAM_CHAT, False),
        ("discord_webhook_url", KEY_NOTIFY_DISCORD_WEBHOOK, True),
        ("gmail_from", KEY_NOTIFY_GMAIL_FROM, False),
        ("gmail_delegated_subject", KEY_NOTIFY_GMAIL_DELEGATED, False),
    ]
    for field, key, secret in mapping:
        val = payload.get(field)
        if val is not None:
            await set_value(db, key, str(val), is_secret=secret, category="notifications")
    recipients = payload.get("gmail_recipients")
    if recipients:
        await set_json(db, KEY_NOTIFY_GMAIL_RECIPIENTS, list(recipients), category="notifications")
    await mark_step(db, "notifications", True)


async def mark_completed(db: AsyncSession) -> None:
    await mark_step(db, "completed", True)
