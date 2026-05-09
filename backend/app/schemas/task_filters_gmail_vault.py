"""Normalización y validación de filters_json para vault ZIP Gmail (Fase 4)."""
from __future__ import annotations

from typing import Any

from app.services import vault_layout

GMAIL_VAULT_ZIP_FILTER_KEYS = frozenset(
    {
        "gmail_vault_packaging",
        "vault_zip_cadence",
        "vault_anchor_dow",
        "bootstrap_upload_immediate",
        "overlap_days",
    }
)

_SCOPES_GMAIL_VAULT = frozenset({"gmail", "full"})


def _parse_bool(v: Any, *, default: bool) -> bool:
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)) and v in (0, 1):
        return bool(int(v))
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("1", "true", "yes", "on"):
            return True
        if s in ("0", "false", "no", "off", ""):
            return False
    return bool(v)


def _parse_int_clamp(v: Any, *, default: int, lo: int, hi: int) -> int:
    if v is None:
        return default
    try:
        n = int(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def normalize_task_filters_for_scope(filters: dict[str, Any], *, scope: str) -> dict[str, Any]:
    """Devuelve una copia de ``filters`` con claves vault-ZIP validadas; falla con ``ValueError``."""
    if not filters:
        return {}
    out = dict(filters)

    uses_zip_keys = bool(GMAIL_VAULT_ZIP_FILTER_KEYS & out.keys())
    if not uses_zip_keys:
        return out

    if scope not in _SCOPES_GMAIL_VAULT:
        raise ValueError(
            "gmail_vault_zip_filters_only_for_gmail_scope: "
            "definí scope «gmail» o «full» para usar gmail_vault_packaging, vault_zip_cadence, etc."
        )

    pkg = out.get("gmail_vault_packaging")
    if pkg is not None:
        p = str(pkg).strip()
        allowed = (
            vault_layout.GMAIL_VAULT_PACKAGING_LEGACY,
            vault_layout.GMAIL_VAULT_PACKAGING_ZIP_ONLY,
            vault_layout.GMAIL_VAULT_PACKAGING_MIXED,
        )
        if p not in allowed:
            raise ValueError(
                f"invalid gmail_vault_packaging: {pkg!r} (esperado uno de {list(allowed)})"
            )
        out["gmail_vault_packaging"] = p

    zip_extra = any(
        k in out
        for k in ("vault_zip_cadence", "vault_anchor_dow", "bootstrap_upload_immediate", "overlap_days")
    )
    if zip_extra and not vault_layout.use_gmail_vault_zip_upload(out):
        raise ValueError(
            "vault_zip_options_require_gmail_vault_packaging_zip_only_or_mixed: "
            "la cadencia ZIP solo aplica con gmail_vault_packaging zip_only o mixed."
        )

    if vault_layout.use_gmail_vault_zip_upload(out):
        raw_c = out.get("vault_zip_cadence")
        c = str(raw_c or "weekly").strip().lower()
        if c not in ("weekly", "monthly", "none"):
            raise ValueError(f"invalid vault_zip_cadence: {raw_c!r} (esperado weekly, monthly o none)")
        out["vault_zip_cadence"] = c
        out["vault_anchor_dow"] = _parse_int_clamp(out.get("vault_anchor_dow"), default=6, lo=0, hi=6)
        out["bootstrap_upload_immediate"] = _parse_bool(
            out.get("bootstrap_upload_immediate"), default=True
        )
        out["overlap_days"] = _parse_int_clamp(out.get("overlap_days"), default=1, lo=0, hi=366)
    else:
        for k in ("vault_zip_cadence", "vault_anchor_dow", "bootstrap_upload_immediate", "overlap_days"):
            out.pop(k, None)

    if out.get("vault_gmail_disable_push") is True and vault_layout.use_gmail_vault_zip_upload(out):
        raise ValueError(
            "gmail_vault_zip_incompatible_with_vault_gmail_disable_push: "
            "desactivá vault_gmail_disable_push o usá solo legacy_eml."
        )

    return out
