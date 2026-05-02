"""Schemas para roles de plataforma (sys_roles)."""
from __future__ import annotations

import re
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

_ROLE_SLUG = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
_RESERVED_ROLE_CODES = frozenset({"super_admin", "operator", "auditor"})


class PermissionBrief(BaseModel):
    code: str
    module: str
    action: str
    description: str | None = None


class RoleOut(BaseModel):
    id: str
    code: str
    name: str
    description: str | None
    is_system: bool
    permissions: list[PermissionBrief]


class RoleCreate(BaseModel):
    code: str = Field(min_length=2, max_length=32)
    name: str = Field(min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=255)
    permission_codes: list[str] = Field(default_factory=list, max_length=256)

    @field_validator("code")
    @classmethod
    def _code(cls, v: str) -> str:
        s = (v or "").strip().lower()
        if not _ROLE_SLUG.match(s):
            raise ValueError("invalid_role_code")
        if s in _RESERVED_ROLE_CODES:
            raise ValueError("reserved_role_code")
        return s


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=255)
    permission_codes: list[str] | None = Field(default=None, max_length=256)
