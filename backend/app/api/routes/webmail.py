"""Webmail access endpoints: magic links, SSO, password management."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_client_ip,
    get_db,
    get_user_agent,
    require_permission,
)
from app.models.accounts import GwAccount
from app.models.enums import AuditAction, WebmailTokenPurpose
from app.models.users import SysUser
from app.schemas.webmail import (
    AdminSsoOut,
    MagicLinkIn,
    MagicLinkOut,
    SetWebmailPasswordIn,
)
from app.services.audit_service import record_audit
from app.services.webmail_service import (
    SSO_JWT_TYPE_ADMIN,
    SSO_JWT_TYPE_CLIENT,
    issue_magic_link,
    issue_sso_jwt,
    set_webmail_password,
)

router = APIRouter(prefix="/webmail", tags=["webmail"])


async def _load_account(db: AsyncSession, account_id: uuid.UUID) -> GwAccount:
    acc = (await db.execute(select(GwAccount).where(GwAccount.id == account_id))).scalar_one_or_none()
    if acc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account_not_found")
    return acc


@router.post(
    "/accounts/{account_id}/password",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def set_password(
    account_id: uuid.UUID,
    payload: SetWebmailPasswordIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("webmail.issue_magic_link")),
) -> None:
    acc = await _load_account(db, account_id)
    try:
        await set_webmail_password(db, account=acc, plaintext=payload.new_password)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    await record_audit(
        db,
        action=AuditAction.SETTING_CHANGED,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        target_table="gw_accounts",
        target_id=str(acc.id),
        message="imap_password_set",
    )
    await db.commit()


@router.post("/accounts/{account_id}/magic-link", response_model=MagicLinkOut)
async def create_magic_link(
    account_id: uuid.UUID,
    payload: MagicLinkIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("webmail.issue_magic_link")),
) -> MagicLinkOut:
    acc = await _load_account(db, account_id)
    purpose = WebmailTokenPurpose(payload.purpose)
    data = await issue_magic_link(
        db,
        account=acc,
        purpose=purpose,
        ttl_minutes=payload.ttl_minutes,
        issued_by_user_id=str(current.id),
    )
    await record_audit(
        db,
        action=AuditAction.WEBMAIL_ACCESSED,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        target_table="gw_accounts",
        target_id=str(acc.id),
        message=f"magic_link_issued:{purpose.value}",
    )
    await db.commit()
    return MagicLinkOut(url=data["url"], expires_at=data["expires_at"])


@router.post("/accounts/{account_id}/sso-admin", response_model=AdminSsoOut)
async def sso_admin(
    account_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("webmail.sso_admin")),
) -> AdminSsoOut:
    acc = await _load_account(db, account_id)
    data = await issue_sso_jwt(email=acc.email, kind=SSO_JWT_TYPE_ADMIN)
    await record_audit(
        db,
        action=AuditAction.WEBMAIL_ACCESSED,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        target_table="gw_accounts",
        target_id=str(acc.id),
        message="admin_sso_issued",
    )
    await db.commit()
    return AdminSsoOut(url=data["url"], expires_at=data["expires_at"])


@router.post("/accounts/{account_id}/sso-client", response_model=AdminSsoOut)
async def sso_client(
    account_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("webmail.issue_magic_link")),
) -> AdminSsoOut:
    acc = await _load_account(db, account_id)
    if not acc.imap_enabled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "webmail_not_provisioned")
    data = await issue_sso_jwt(email=acc.email, kind=SSO_JWT_TYPE_CLIENT)
    await record_audit(
        db,
        action=AuditAction.WEBMAIL_ACCESSED,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        target_table="gw_accounts",
        target_id=str(acc.id),
        message="client_sso_issued",
    )
    await db.commit()
    return AdminSsoOut(url=data["url"], expires_at=data["expires_at"])
