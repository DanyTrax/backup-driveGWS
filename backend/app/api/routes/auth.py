"""Authentication endpoints: login, refresh, logout, MFA, password."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_client_ip,
    get_current_user,
    get_db,
    get_user_agent,
    get_user_permissions,
    rate_limit,
)
from app.core.config import get_settings
from app.models.users import SysUser
from app.schemas.auth import (
    LoginRequest,
    MfaEnrollConfirm,
    MfaEnrollResult,
    MfaEnrollStart,
    PasswordChangeRequest,
    ProfileOut,
    RefreshRequest,
    TokenPair,
)
from app.services import auth_service as auth
from app.services.auth_service import (
    AccountLocked,
    AccountSuspended,
    InvalidCredentials,
    InvalidMfaCode,
    MfaRequired,
)

settings = get_settings()
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenPair)
async def login(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _rl=Depends(
        rate_limit(
            "login",
            limit=settings.rate_limit_login_per_minute,
            window_seconds=60,
        )
    ),
) -> TokenPair:
    try:
        tokens = await auth.authenticate(
            db,
            payload.email,
            payload.password,
            payload.mfa_code,
            ip=get_client_ip(request),
            user_agent=get_user_agent(request),
        )
    except MfaRequired as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail={"error": "mfa_required", "user_id": exc.user_id},
        ) from exc
    except InvalidMfaCode as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_mfa_code"},
        ) from exc
    except AccountLocked as exc:
        raise HTTPException(
            status.HTTP_423_LOCKED,
            detail={
                "error": "account_locked",
                "retry_after_seconds": exc.retry_after_seconds,
            },
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except AccountSuspended as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail={"error": "account_suspended"}
        ) from exc
    except InvalidCredentials as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail={"error": "invalid_credentials"}
        ) from exc

    return TokenPair(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    payload: RefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenPair:
    try:
        tokens = await auth.refresh_tokens(
            db,
            payload.refresh_token,
            ip=get_client_ip(request),
            user_agent=get_user_agent(request),
        )
    except InvalidCredentials as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return TokenPair(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def logout(
    payload: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> None:
    await auth.revoke_session(db, payload.refresh_token)


@router.get("/me", response_model=ProfileOut)
async def me(user: SysUser = Depends(get_current_user)) -> ProfileOut:
    return ProfileOut(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        role_code=user.role_code,
        mfa_enabled=user.mfa_enabled,
        must_change_password=user.must_change_password,
        status=user.status,
        last_login_at=user.last_login_at,
        preferred_locale=user.preferred_locale,
        preferred_timezone=user.preferred_timezone,
        permissions=sorted(get_user_permissions(user)),
    )


@router.post("/mfa/enroll/start", response_model=MfaEnrollStart)
async def mfa_enroll_start(user: SysUser = Depends(get_current_user)) -> MfaEnrollStart:
    data = await auth.start_mfa_enrollment(user)
    return MfaEnrollStart(**data)


@router.post("/mfa/enroll/confirm", response_model=MfaEnrollResult)
async def mfa_enroll_confirm(
    payload: MfaEnrollConfirm,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: SysUser = Depends(get_current_user),
) -> MfaEnrollResult:
    secret = request.headers.get("X-MFA-Secret")
    if not secret:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "missing_mfa_secret_header")
    try:
        codes = await auth.confirm_mfa_enrollment(db, user, secret, payload.code)
    except InvalidMfaCode as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_mfa_code") from exc
    return MfaEnrollResult(backup_codes=codes)


@router.post(
    "/mfa/disable",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def mfa_disable(
    payload: MfaEnrollConfirm,
    db: AsyncSession = Depends(get_db),
    user: SysUser = Depends(get_current_user),
) -> None:
    if not user.mfa_enabled or not user.mfa_secret_encrypted:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "mfa_not_enabled")
    from app.core.crypto import decrypt_str
    from app.core.security import verify_totp

    secret = decrypt_str(user.mfa_secret_encrypted)
    if not verify_totp(secret, payload.code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_mfa_code")
    await auth.disable_mfa(db, user)


@router.post(
    "/password/change",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def password_change(
    payload: PasswordChangeRequest,
    db: AsyncSession = Depends(get_db),
    user: SysUser = Depends(get_current_user),
) -> None:
    try:
        await auth.change_password(db, user, payload.current_password, payload.new_password)
    except InvalidCredentials as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
