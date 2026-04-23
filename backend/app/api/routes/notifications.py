"""In-app notifications endpoints + channel test hooks."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.api.deps import get_current_user, get_db, require_permission
from app.models.notifications import Notification, SysUserNotificationPref
from app.models.users import SysUser

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationOut(BaseModel):
    id: str
    category: str
    severity: str
    title: str
    body: str | None
    action_url: str | None
    created_at: datetime
    read_at: datetime | None


class PrefsIn(BaseModel):
    channels_matrix: dict[str, list[str]]
    quiet_hours: list[dict] = []
    digest_enabled: bool = False
    digest_frequency: str = "daily"
    telegram_chat_id: str | None = None
    discord_webhook_url: str | None = None
    gmail_recipient: str | None = None


class PrefsOut(PrefsIn):
    pass


def _to_out(n: Notification) -> NotificationOut:
    return NotificationOut(
        id=str(n.id),
        category=n.category,
        severity=n.severity,
        title=n.title,
        body=n.body,
        action_url=n.action_url,
        created_at=n.created_at,
        read_at=n.read_at,
    )


@router.get("", response_model=list[NotificationOut])
async def list_mine(
    unread: bool = False,
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
    user: SysUser = Depends(get_current_user),
) -> list[NotificationOut]:
    stmt = (
        select(Notification)
        .where(Notification.recipient_user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    if unread:
        stmt = stmt.where(Notification.read_at.is_(None))
    rows = (await db.execute(stmt)).scalars().all()
    return [_to_out(n) for n in rows]


@router.post(
    "/mark-read",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def mark_read(
    ids: list[uuid.UUID],
    db: AsyncSession = Depends(get_db),
    user: SysUser = Depends(get_current_user),
) -> None:
    from datetime import timezone as _tz

    stmt = select(Notification).where(
        Notification.id.in_(ids), Notification.recipient_user_id == user.id
    )
    rows = (await db.execute(stmt)).scalars().all()
    now = datetime.now(_tz.utc)
    for n in rows:
        n.read_at = now
    await db.commit()


@router.get("/prefs", response_model=PrefsOut)
async def get_prefs(
    db: AsyncSession = Depends(get_db),
    user: SysUser = Depends(get_current_user),
) -> PrefsOut:
    stmt = select(SysUserNotificationPref).where(SysUserNotificationPref.user_id == user.id)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        return PrefsOut(channels_matrix={})
    return PrefsOut(
        channels_matrix=row.channels_matrix_json or {},
        quiet_hours=list(row.quiet_hours_json or []),
        digest_enabled=row.digest_enabled,
        digest_frequency=row.digest_frequency,
        telegram_chat_id=row.telegram_chat_id,
        discord_webhook_url=row.discord_webhook_url,
        gmail_recipient=row.gmail_recipient,
    )


@router.put("/prefs", response_model=PrefsOut)
async def set_prefs(
    payload: PrefsIn,
    db: AsyncSession = Depends(get_db),
    user: SysUser = Depends(get_current_user),
) -> PrefsOut:
    stmt = select(SysUserNotificationPref).where(SysUserNotificationPref.user_id == user.id)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        row = SysUserNotificationPref(user_id=user.id)
        db.add(row)
    row.channels_matrix_json = payload.channels_matrix
    row.quiet_hours_json = payload.quiet_hours
    row.digest_enabled = payload.digest_enabled
    row.digest_frequency = payload.digest_frequency
    row.telegram_chat_id = payload.telegram_chat_id
    row.discord_webhook_url = payload.discord_webhook_url
    row.gmail_recipient = payload.gmail_recipient
    await db.commit()
    return payload  # type: ignore[return-value]


@router.post(
    "/test/{channel}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def test_channel(
    channel: str,
    db: AsyncSession = Depends(get_db),
    _u: SysUser = Depends(require_permission("notifications.manage_global")),
) -> None:
    from app.services.channels import discord as discord_ch, gmail_api, telegram

    if channel == "telegram":
        ok = await telegram.send(db, title="MSA Test", body="Canal Telegram operativo")
    elif channel == "discord":
        ok = await discord_ch.send(db, title="MSA Test", body="Canal Discord operativo")
    elif channel == "gmail":
        ok = await gmail_api.send(db, subject="MSA Test", body="Canal Gmail operativo")
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unsupported_channel")
    if not ok:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"{channel}_send_failed")
