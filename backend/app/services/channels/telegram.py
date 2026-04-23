"""Telegram Bot notification channel."""
from __future__ import annotations

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.settings_service import (
    KEY_NOTIFY_TELEGRAM_BOT,
    KEY_NOTIFY_TELEGRAM_CHAT,
    get_value,
)


async def send(db: AsyncSession, *, title: str, body: str, chat_id: str | None = None) -> bool:
    bot_token = await get_value(db, KEY_NOTIFY_TELEGRAM_BOT)
    chat = chat_id or await get_value(db, KEY_NOTIFY_TELEGRAM_CHAT)
    if not bot_token or not chat:
        return False
    text = f"*{title}*\n{body}" if body else f"*{title}*"
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat, "text": text, "parse_mode": "Markdown"}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json=payload)
    return resp.status_code == 200
