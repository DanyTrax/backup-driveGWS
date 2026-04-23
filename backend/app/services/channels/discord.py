"""Discord webhook notification channel."""
from __future__ import annotations

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.settings_service import KEY_NOTIFY_DISCORD_WEBHOOK, get_value


async def send(db: AsyncSession, *, title: str, body: str, webhook_url: str | None = None) -> bool:
    url = webhook_url or await get_value(db, KEY_NOTIFY_DISCORD_WEBHOOK)
    if not url:
        return False
    content = f"**{title}**\n{body}" if body else f"**{title}**"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json={"content": content[:1900]})
    return resp.status_code in (200, 204)
