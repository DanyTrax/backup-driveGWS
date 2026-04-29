"""Reusable FastAPI dependencies."""
from __future__ import annotations

import ipaddress
import uuid
from collections.abc import AsyncGenerator, Callable
from typing import Any

from fastapi import Depends, HTTPException, Request, WebSocket, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.permissions_catalog import DEFAULT_ROLE_PERMISSIONS
from app.core.security import decode_token
from app.models.enums import UserRole
from app.models.users import SysRole, SysUser
from app.services.rate_limit import check_rate_limit

_bearer = HTTPBearer(auto_error=False)


def _parse_inet_ip(raw: str | None) -> str | None:
    """Devuelve una IP válida para columnas PostgreSQL INET, o None.

    Evita 500 si el proxy manda basura en ``X-Forwarded-For`` (vacío, hostname, etc.).
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if "%" in s:
        s = s.split("%", 1)[0]
    try:
        return str(ipaddress.ip_address(s))
    except ValueError:
        pass
    if s.count(":") == 1 and "." in s.split(":", 1)[0]:
        host = s.rsplit(":", 1)[0]
        try:
            return str(ipaddress.ip_address(host))
        except ValueError:
            return None
    return None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


def get_client_ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        for part in fwd.split(","):
            parsed = _parse_inet_ip(part)
            if parsed:
                return parsed
    if request.client and request.client.host:
        return _parse_inet_ip(request.client.host)
    return None


def get_user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


async def _load_current_user(
    db: AsyncSession, user_id: str, expected_role: str | None
) -> SysUser:
    try:
        uid = uuid.UUID(user_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_token") from exc

    stmt = (
        select(SysUser)
        .options(selectinload(SysUser.role).selectinload(SysRole.permissions))
        .where(SysUser.id == uid)
    )
    user = (await db.execute(stmt)).scalar_one_or_none()
    if user is None or user.status != "active":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "inactive_user")
    if expected_role and user.role_code != expected_role:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "role_mismatch")
    return user


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> SysUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing_token")
    try:
        payload = decode_token(credentials.credentials, expected_type="access")
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    user = await _load_current_user(db, payload.sub, payload.role)
    request.state.current_user = user
    return user


def get_user_permissions(user: SysUser) -> set[str]:
    perms: set[str] = set()
    if user.role is not None and user.role.permissions:
        perms.update(p.code for p in user.role.permissions)
    # Fallback for safety: merge catalog defaults if DB seed is partial.
    try:
        role_enum = UserRole(user.role_code)
        perms |= set(DEFAULT_ROLE_PERMISSIONS.get(role_enum, frozenset()))
    except ValueError:
        pass
    return perms


def require_permission(*codes: str) -> Callable[[SysUser], SysUser]:
    """Dependency factory. Usage: `Depends(require_permission("users.edit"))`."""

    async def _dep(user: SysUser = Depends(get_current_user)) -> SysUser:
        perms = get_user_permissions(user)
        missing = [c for c in codes if c not in perms]
        if missing:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail={"error": "forbidden", "missing": missing},
            )
        return user

    return _dep


def require_any_permission(*codes: str) -> Callable[[SysUser], SysUser]:
    """Al menos uno de los permisos listados (útil para flujos webmail vs cuentas)."""

    async def _dep(user: SysUser = Depends(get_current_user)) -> SysUser:
        perms = get_user_permissions(user)
        if not any(c in perms for c in codes):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail={"error": "forbidden", "missing": list(codes)},
            )
        return user

    return _dep


async def mailbox_reader_for_path_account(
    account_id: uuid.UUID,
    user: SysUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SysUser:
    perms = get_user_permissions(user)
    if "mailbox.view_all" in perms:
        return user
    if "mailbox.view_delegated" in perms:
        from app.models.mailbox_delegation import SysUserMailboxDelegation

        stmt = (
            select(SysUserMailboxDelegation.id)
            .where(
                SysUserMailboxDelegation.sys_user_id == user.id,
                SysUserMailboxDelegation.gw_account_id == account_id,
            )
            .limit(1)
        )
        if (await db.execute(stmt)).scalar_one_or_none() is not None:
            return user
    raise HTTPException(
        status.HTTP_403_FORBIDDEN,
        detail={"error": "mailbox_forbidden", "missing": ["mailbox.view_all", "mailbox.view_delegated"]},
    )


def require_role(*roles: UserRole) -> Callable[[SysUser], SysUser]:
    async def _dep(user: SysUser = Depends(get_current_user)) -> SysUser:
        if user.role_code not in {r.value for r in roles}:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "forbidden")
        return user

    return _dep


async def rate_limit_dep(
    request: Request,
    *,
    key_prefix: str,
    limit: int,
    window_seconds: int,
) -> None:
    ip = get_client_ip(request) or "anon"
    result = await check_rate_limit(f"{key_prefix}:{ip}", limit, window_seconds)
    if not result.allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limited",
                "retry_after_seconds": result.reset_in_seconds,
            },
            headers={"Retry-After": str(result.reset_in_seconds)},
        )


def rate_limit(key_prefix: str, *, limit: int, window_seconds: int) -> Callable[..., Any]:
    async def _dep(request: Request) -> None:
        await rate_limit_dep(
            request,
            key_prefix=key_prefix,
            limit=limit,
            window_seconds=window_seconds,
        )

    return _dep


async def get_current_user_ws(
    websocket: WebSocket,
    db: AsyncSession,
    token: str | None,
) -> SysUser | None:
    """Parse `?token=` for WebSocket connections."""
    if not token:
        return None
    try:
        payload = decode_token(token, expected_type="access")
    except ValueError:
        return None
    try:
        return await _load_current_user(db, payload.sub, payload.role)
    except HTTPException:
        return None


_settings = get_settings()
