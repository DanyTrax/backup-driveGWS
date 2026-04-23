"""Typed helpers over the sys_settings table."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.settings import SysSetting


async def get_setting(db: AsyncSession, key: str) -> SysSetting | None:
    return (await db.execute(select(SysSetting).where(SysSetting.key == key))).scalar_one_or_none()


async def get_value(db: AsyncSession, key: str, default: Any = None) -> Any:
    row = await get_setting(db, key)
    if row is None:
        return default
    return row.get_plaintext() if row.value is not None else default


async def get_json(db: AsyncSession, key: str, default: Any = None) -> Any:
    raw = await get_value(db, key)
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default


async def set_value(
    db: AsyncSession,
    key: str,
    value: str | None,
    *,
    is_secret: bool = False,
    category: str = "general",
    description: str | None = None,
    actor_user_id: str | None = None,
) -> SysSetting:
    row = await get_setting(db, key)
    if row is None:
        row = SysSetting(
            key=key,
            is_secret=is_secret,
            category=category,
            description=description,
        )
        db.add(row)
        await db.flush()
    row.is_secret = is_secret
    row.category = category
    if description is not None:
        row.description = description
    if actor_user_id is not None:
        import uuid

        row.updated_by_user_id = uuid.UUID(actor_user_id)
    row.set_plaintext(value)
    await db.flush()
    return row


async def set_json(
    db: AsyncSession,
    key: str,
    value: Any,
    *,
    is_secret: bool = False,
    category: str = "general",
    **kwargs: Any,
) -> SysSetting:
    return await set_value(
        db,
        key,
        json.dumps(value, ensure_ascii=False),
        is_secret=is_secret,
        category=category,
        **kwargs,
    )


# ---- Well-known keys --------------------------------------------------------
KEY_GOOGLE_SA_JSON = "google.service_account_json"
KEY_GOOGLE_DELEGATED_ADMIN = "google.delegated_admin_email"
KEY_GOOGLE_CUSTOMER_ID = "google.customer_id"
KEY_VAULT_SHARED_DRIVE_ID = "vault.shared_drive_id"
KEY_VAULT_ROOT_FOLDER_ID = "vault.root_folder_id"
KEY_VAULT_LAYOUT = "vault.layout"
KEY_SETUP_STATE = "setup.state"
KEY_NOTIFY_TELEGRAM_BOT = "notify.telegram.bot_token"
KEY_NOTIFY_TELEGRAM_CHAT = "notify.telegram.chat_id"
KEY_NOTIFY_DISCORD_WEBHOOK = "notify.discord.webhook_url"
KEY_NOTIFY_GMAIL_FROM = "notify.gmail.from_address"
KEY_NOTIFY_GMAIL_DELEGATED = "notify.gmail.delegated_subject"
KEY_NOTIFY_GMAIL_RECIPIENTS = "notify.gmail.recipients"
KEY_PLATFORM_BACKUP_DEST = "platform_backup.destination_folder_id"
