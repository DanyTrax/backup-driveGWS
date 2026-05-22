"""Generación de mapas Rspamd (dominios / correos) para multimap HTTP."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable

# Dominio: etiquetas DNS razonables (no IDN completo; suficiente para PoC).
_DOMAIN_RE = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$",
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class WhitelistEntryKind(str, Enum):
    domain = "domain"
    email = "email"


@dataclass(frozen=True, slots=True)
class NormalizedWhitelistEntry:
    kind: WhitelistEntryKind
    value: str
    raw_input: str


class WhitelistNormalizeError(ValueError):
    def __init__(self, message: str, *, raw: str) -> None:
        super().__init__(message)
        self.raw = raw


def _strip_input(line: str) -> str:
    return line.strip().strip('"').strip("'")


def normalize_whitelist_input(raw: str) -> NormalizedWhitelistEntry:
    """
    Acepta entradas humanas y devuelve forma canónica para Rspamd.

    - dominio.com, @dominio.com, *@dominio.com → dominio (mapa email:domain)
    - user@dominio.com → correo (mapa filter=email)
    """
    s = _strip_input(raw)
    if not s or s.startswith("#"):
        raise WhitelistNormalizeError("entrada vacía o comentario", raw=raw)

    lower = s.lower()

    if lower.startswith("*@"):
        domain = lower[2:].strip()
    elif lower.startswith("@"):
        domain = lower[1:].strip()
    elif "@" in lower:
        if lower.count("@") != 1:
            raise WhitelistNormalizeError("correo o dominio inválido (múltiples @)", raw=raw)
        local, domain = lower.split("@", 1)
        if not local:
            raise WhitelistNormalizeError("falta parte local antes de @", raw=raw)
        if not domain or "." not in domain:
            raise WhitelistNormalizeError("dominio inválido", raw=raw)
        email = f"{local}@{domain}"
        if not _EMAIL_RE.match(email):
            raise WhitelistNormalizeError("correo inválido", raw=raw)
        return NormalizedWhitelistEntry(WhitelistEntryKind.email, email, raw)

    domain = lower
    if domain.startswith("*."):
        domain = domain[2:]
    if not _DOMAIN_RE.match(domain):
        raise WhitelistNormalizeError(
            "dominio inválido (use algo como cliente.com, sin http://)",
            raw=raw,
        )
    return NormalizedWhitelistEntry(WhitelistEntryKind.domain, domain, raw)


def parse_env_entry_lines(blob: str) -> list[NormalizedWhitelistEntry]:
    """Parsea líneas separadas por newline o coma desde .env (PoC)."""
    out: list[NormalizedWhitelistEntry] = []
    seen: set[tuple[WhitelistEntryKind, str]] = set()
    for chunk in blob.replace(",", "\n").splitlines():
        line = chunk.strip()
        if not line or line.startswith("#"):
            continue
        try:
            ent = normalize_whitelist_input(line)
        except WhitelistNormalizeError:
            continue
        key = (ent.kind, ent.value)
        if key in seen:
            continue
        seen.add(key)
        out.append(ent)
    return out


def render_rspamd_map(
    entries: Iterable[NormalizedWhitelistEntry],
    *,
    kind: WhitelistEntryKind,
    title: str,
) -> str:
    """Texto plano: una línea por entrada, formato Rspamd."""
    lines = [
        f"# {title}",
        f"# generated_at: {datetime.now(timezone.utc).isoformat()}",
        "# format: one entry per line; do not edit manually (managed by platform PoC)",
    ]
    for ent in entries:
        if ent.kind == kind:
            lines.append(ent.value)
    lines.append("")
    return "\n".join(lines)


def split_entries(
    entries: Iterable[NormalizedWhitelistEntry],
) -> tuple[list[str], list[str]]:
    domains: list[str] = []
    emails: list[str] = []
    for ent in entries:
        if ent.kind == WhitelistEntryKind.domain:
            domains.append(ent.value)
        else:
            emails.append(ent.value)
    return domains, emails
