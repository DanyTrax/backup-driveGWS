"""Branding del panel (nombre, colores, logo)."""
from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

_HEX_COLOR = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


class BrandingUpdate(BaseModel):
    app_name: str | None = Field(default=None, max_length=120)
    primary_color: str | None = Field(default=None, max_length=32)
    accent_color: str | None = Field(default=None, max_length=32)
    """URL absoluta del logo (https://…). Vacío = quitar URL (se puede usar solo archivo subido)."""
    logo_url: str | None = Field(default=None, max_length=2000)

    @field_validator("primary_color", "accent_color")
    @classmethod
    def _hex(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return v
        t = v.strip()
        if not _HEX_COLOR.match(t):
            raise ValueError("color_must_be_hex")
        return t

    @field_validator("logo_url")
    @classmethod
    def _logo_url(cls, v: str | None) -> str | None:
        if v is None:
            return None
        t = v.strip()
        if not t:
            return ""
        if not (t.startswith("http://") or t.startswith("https://") or t.startswith("/")):
            raise ValueError("logo_url_must_be_http_or_path")
        return t


class BrandingConfigOut(BaseModel):
    """Valores guardados para editar en el panel (no necesariamente igual al logo efectivo público)."""

    app_name: str
    primary_color: str
    accent_color: str
    logo_url_external: str = ""
    has_uploaded_logo: bool = False
