"""Rutas Maildir alineadas con Dovecot (user_query: home sin /Maildir, mail = maildir:home/Maildir)."""
from __future__ import annotations

from pathlib import Path

from app.models.accounts import GwAccount


def maildir_home_from_email(email: str) -> str:
    email = email.strip().lower()
    if "@" not in email:
        raise ValueError("invalid_email")
    local, domain = email.split("@", 1)
    if not local or not domain:
        raise ValueError("invalid_email")
    return f"/var/mail/vhosts/{domain}/{local}"


def maildir_home_for_account(account: GwAccount) -> str:
    raw = (account.maildir_path or "").strip()
    if raw:
        p = Path(raw)
        if p.name == "Maildir":
            return str(p.parent)
        return raw.rstrip("/")
    return maildir_home_from_email(account.email)


def maildir_root_for_account(account: GwAccount) -> Path:
    """Directorio Maildir real (contiene cur, new, tmp)."""
    home = maildir_home_for_account(account)
    return Path(home) / "Maildir"
