"""Webmail access endpoints: magic links, SSO, password management."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_client_ip,
    get_db,
    get_user_agent,
    rate_limit,
    require_permission,
)
from app.core.config import get_settings
from app.models.accounts import GwAccount
from app.models.enums import AuditAction, WebmailTokenPurpose
from app.models.users import SysUser
from app.schemas.webmail import (
    AdminSsoOut,
    MagicLinkIn,
    MagicLinkOut,
    PasswordAssignLinkIn,
    PasswordAssignLinkOut,
    PasswordSetupCompleteIn,
    PasswordSetupPeekOut,
    SetWebmailPasswordIn,
)
from app.services.audit_service import record_audit
from app.services.webmail_service import (
    PASSWORD_ASSIGN_TTL_MAX_MINUTES,
    SSO_JWT_TYPE_ADMIN,
    SSO_JWT_TYPE_CLIENT,
    complete_password_setup,
    issue_magic_link,
    issue_password_assign_link,
    issue_sso_jwt,
    peek_password_setup,
    redeem_magic_link,
    set_webmail_password,
)

router = APIRouter(prefix="/webmail", tags=["webmail"])


def _public_site_base(request: Request) -> str:
    """Origen de la SPA: DOMAIN_PLATFORM (no DOMAIN_WEBMAIL). Asignar clave: .../webmail/assign-password."""
    settings = get_settings()
    p = settings.platform_public_origin
    if p:
        return p
    scheme = (request.headers.get("x-forwarded-proto") or "https").split(",")[0].strip() or "https"
    host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc or "").split(",")[
        0
    ].strip()
    if not host:
        return "https://localhost"
    return f"{scheme}://{host}".rstrip("/")


@router.get("/magic-redeem")
async def magic_link_redeem(
    request: Request,
    token: str,
    purpose: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Canjea token de un solo uso (magic link) y redirige a Roundcube con JWT SSO.

    Debe estar en el host de la API (DOMAIN_PLATFORM), no en el de webmail.
    """
    try:
        pur = WebmailTokenPurpose(purpose)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_purpose") from exc
    if pur is WebmailTokenPurpose.PASSWORD_ASSIGN:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Este enlace se usa en la plataforma (asignar contraseña en el navegador), no al abrirse desde /magic-redeem.",
        )
    try:
        acc = await redeem_magic_link(
            db,
            token=token,
            purpose=pur,
            consumer_ip=get_client_ip(request),
            consumer_user_agent=get_user_agent(request),
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await db.commit()

    if pur in (WebmailTokenPurpose.FIRST_SETUP, WebmailTokenPurpose.PASSWORD_RESET):
        kind = SSO_JWT_TYPE_ADMIN
    elif pur == WebmailTokenPurpose.CLIENT_SSO:
        kind = SSO_JWT_TYPE_CLIENT
    else:
        kind = SSO_JWT_TYPE_ADMIN
    data = await issue_sso_jwt(email=acc.email, kind=kind)
    return RedirectResponse(url=data["url"], status_code=302)


async def _load_account(db: AsyncSession, account_id: uuid.UUID) -> GwAccount:
    acc = (await db.execute(select(GwAccount).where(GwAccount.id == account_id))).scalar_one_or_none()
    if acc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account_not_found")
    return acc


@router.post(
    "/accounts/{account_id}/password",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
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


@router.post("/accounts/{account_id}/password-assign-link", response_model=PasswordAssignLinkOut)
async def create_password_assign_link(
    account_id: uuid.UUID,
    payload: PasswordAssignLinkIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: SysUser = Depends(require_permission("webmail.issue_magic_link")),
) -> PasswordAssignLinkOut:
    """Emite enlace a la landing pública (máx. 24 h) para que el usuario fije la clave IMAP."""
    acc = await _load_account(db, account_id)
    ttl_h = int(payload.ttl_hours)
    ttl_m = min(ttl_h * 60, PASSWORD_ASSIGN_TTL_MAX_MINUTES)
    data = await issue_password_assign_link(
        db,
        account=acc,
        site_root=_public_site_base(request),
        ttl_minutes=ttl_m,
        issued_by_user_id=str(current.id),
    )
    await record_audit(
        db,
        action=AuditAction.SETTING_CHANGED,
        actor_user_id=current.id,
        actor_label=current.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        target_table="gw_accounts",
        target_id=str(acc.id),
        message="password_assign_link_issued",
    )
    await db.commit()
    return PasswordAssignLinkOut(
        url=data["url"],
        expires_at=data["expires_at"],
        ttl_minutes=int(data["ttl_minutes"]),
    )


@router.get("/password-setup/status", response_model=PasswordSetupPeekOut)
async def password_setup_status(
    token: str,
    db: AsyncSession = Depends(get_db),
    _rl: None = Depends(
        rate_limit("webmail_pwd_status", limit=60, window_seconds=3600),
    ),
) -> PasswordSetupPeekOut:
    r = await peek_password_setup(db, token=token)
    return PasswordSetupPeekOut(
        ok=r.ok,
        email=r.email,
        expires_at=r.expires_at,
        reason=r.reason,
    )


@router.post(
    "/password-setup/complete",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def password_setup_complete(
    request: Request,
    payload: PasswordSetupCompleteIn,
    db: AsyncSession = Depends(get_db),
    _rl: None = Depends(
        rate_limit("webmail_pwd_set", limit=20, window_seconds=3600),
    ),
) -> None:
    try:
        acc_id = await complete_password_setup(
            db,
            token=payload.token,
            plaintext=payload.new_password,
            consumer_ip=get_client_ip(request),
            consumer_user_agent=get_user_agent(request),
        )
    except ValueError as exc:
        code = str(exc)
        if code in ("token_expired", "token_already_used", "invalid_token"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, code) from exc
        if code == "password_too_short":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, code) from exc
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "set_failed") from exc
    await record_audit(
        db,
        action=AuditAction.SETTING_CHANGED,
        actor_user_id=None,
        actor_label="user_password_assign_link",
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        target_table="gw_accounts",
        target_id=str(acc_id),
        message="imap_password_set_via_landing",
    )
    await db.commit()
