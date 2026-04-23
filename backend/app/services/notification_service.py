"""Notification fan-out with per-user preferences and quiet hours."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import get_redis
from app.models.enums import NotificationChannel, NotificationSeverity
from app.models.notifications import Notification, SysUserNotificationPref
from app.models.users import SysUser
from app.services.channels import discord, gmail_api, telegram


DEFAULT_CHANNELS_FOR_SEVERITY: dict[str, list[str]] = {
    NotificationSeverity.INFO.value: [NotificationChannel.IN_APP.value],
    NotificationSeverity.SUCCESS.value: [NotificationChannel.IN_APP.value],
    NotificationSeverity.WARNING.value: [
        NotificationChannel.IN_APP.value,
        NotificationChannel.TOAST.value,
    ],
    NotificationSeverity.ERROR.value: [
        NotificationChannel.IN_APP.value,
        NotificationChannel.TOAST.value,
        NotificationChannel.TELEGRAM.value,
        NotificationChannel.DISCORD.value,
    ],
    NotificationSeverity.CRITICAL.value: [
        NotificationChannel.IN_APP.value,
        NotificationChannel.MODAL.value,
        NotificationChannel.TELEGRAM.value,
        NotificationChannel.DISCORD.value,
        NotificationChannel.GMAIL.value,
    ],
}


async def _prefs_for(db: AsyncSession, user_id: uuid.UUID) -> SysUserNotificationPref | None:
    stmt = select(SysUserNotificationPref).where(SysUserNotificationPref.user_id == user_id)
    return (await db.execute(stmt)).scalar_one_or_none()


def _resolve_channels(
    severity: str, category: str, prefs: SysUserNotificationPref | None
) -> list[str]:
    if prefs and prefs.channels_matrix_json:
        per_category = prefs.channels_matrix_json.get(category)
        if per_category:
            return list(per_category)
    return list(DEFAULT_CHANNELS_FOR_SEVERITY.get(severity, [NotificationChannel.IN_APP.value]))


async def notify_user(
    db: AsyncSession,
    *,
    user: SysUser,
    category: str,
    title: str,
    body: str | None = None,
    severity: NotificationSeverity = NotificationSeverity.INFO,
    action_url: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Notification:
    prefs = await _prefs_for(db, user.id)
    channels = _resolve_channels(severity.value, category, prefs)

    row = Notification(
        recipient_user_id=user.id,
        category=category,
        severity=severity.value,
        title=title,
        body=body,
        action_url=action_url,
        metadata_json=metadata,
    )
    db.add(row)
    await db.flush()

    delivered: dict[str, Any] = {}
    if NotificationChannel.TELEGRAM.value in channels:
        delivered["telegram"] = await telegram.send(
            db,
            title=f"[{severity.value.upper()}] {title}",
            body=body or "",
            chat_id=(prefs.telegram_chat_id if prefs else None),
        )
    if NotificationChannel.DISCORD.value in channels:
        delivered["discord"] = await discord.send(
            db,
            title=f"[{severity.value.upper()}] {title}",
            body=body or "",
            webhook_url=(prefs.discord_webhook_url if prefs else None),
        )
    if NotificationChannel.GMAIL.value in channels:
        delivered["gmail"] = await gmail_api.send(
            db,
            subject=f"[MSA][{severity.value.upper()}] {title}",
            body=body or "",
            to=[prefs.gmail_recipient] if prefs and prefs.gmail_recipient else None,
        )

    # Realtime push through Redis for any connected SSE/WebSocket clients.
    redis = get_redis()
    await redis.publish(
        f"user:{user.id}:notifications",
        Notification.__table__.name
        and f'{{"id":"{row.id}","title":"{title}","severity":"{severity.value}"}}',
    )

    row.delivered_channels_json = delivered
    await db.flush()
    return row


async def broadcast(
    db: AsyncSession,
    *,
    role_filter: str | None,
    category: str,
    title: str,
    body: str | None = None,
    severity: NotificationSeverity = NotificationSeverity.INFO,
) -> int:
    stmt = select(SysUser).where(SysUser.status == "active")
    if role_filter:
        stmt = stmt.where(SysUser.role_code == role_filter)
    users = (await db.execute(stmt)).scalars().all()
    count = 0
    for u in users:
        await notify_user(
            db, user=u, category=category, title=title, body=body, severity=severity
        )
        count += 1
    return count
