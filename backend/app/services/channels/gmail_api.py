"""Gmail API notification channel (uses the Workspace SA with DWD)."""
from __future__ import annotations

import asyncio
import base64
import json
from email.message import EmailMessage

from googleapiclient.discovery import build
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.google.credentials import gmail_send_credentials
from app.services.settings_service import (
    KEY_NOTIFY_GMAIL_DELEGATED,
    KEY_NOTIFY_GMAIL_FROM,
    KEY_NOTIFY_GMAIL_RECIPIENTS,
    get_value,
)


async def send(
    db: AsyncSession,
    *,
    subject: str,
    body: str,
    to: list[str] | None = None,
) -> bool:
    delegated = await get_value(db, KEY_NOTIFY_GMAIL_DELEGATED)
    from_addr = await get_value(db, KEY_NOTIFY_GMAIL_FROM) or delegated
    if not delegated or not from_addr:
        return False

    if to is None:
        recipients_raw = await get_value(db, KEY_NOTIFY_GMAIL_RECIPIENTS)
        if recipients_raw:
            try:
                to = json.loads(recipients_raw)
            except json.JSONDecodeError:
                to = [recipients_raw]
        else:
            to = [delegated]
    if not to:
        return False

    creds = await gmail_send_credentials(db, delegated)
    service = await asyncio.to_thread(
        lambda: build("gmail", "v1", credentials=creds, cache_discovery=False)
    )

    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    msg.set_content(body)
    encoded = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")

    def _send():
        return service.users().messages().send(userId="me", body={"raw": encoded}).execute()

    try:
        await asyncio.to_thread(_send)
        return True
    except Exception:
        return False
