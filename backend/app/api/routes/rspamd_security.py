"""
Feeds HTTP para Rspamd (multimap). Sin prefijo /api — montado en /security.

PoC: listas desde variables de entorno hasta tener CRUD en panel.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse, Response

from app.core.config import get_settings
from app.services.rspamd_whitelist_service import (
    WhitelistEntryKind,
    WhitelistNormalizeError,
    normalize_whitelist_input,
    parse_env_entry_lines,
    render_rspamd_map,
    split_entries,
)

router = APIRouter(prefix="/security", tags=["rspamd-security"])


def _verify_feed_token(token: str | None) -> None:
    settings = get_settings()
    expected = (settings.rspamd_whitelist_feed_token or "").strip()
    if not expected:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "whitelist_feed_disabled",
                "message": "Definí RSPAMD_WHITELIST_FEED_TOKEN en .env y reiniciá app.",
            },
        )
    if not token or token.strip() != expected:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="invalid_or_missing_token")


def _entries_from_env() -> list:
    settings = get_settings()
    blob = (settings.rspamd_whitelist_entries or "").strip()
    if not blob:
        return []
    return parse_env_entry_lines(blob)


def _plain_map_response(body: str, *, head_only: bool) -> PlainTextResponse:
    """Rspamd HTTP maps suelen usar HEAD (ETag); sin HEAD devuelve 405 y el mapa queda Not loaded."""
    headers = {"Cache-Control": "no-store"}
    if head_only:
        headers["Content-Length"] = str(len(body.encode("utf-8")))
        return PlainTextResponse(
            content="",
            media_type="text/plain; charset=utf-8",
            headers=headers,
        )
    return PlainTextResponse(
        content=body,
        media_type="text/plain; charset=utf-8",
        headers=headers,
    )


@router.api_route(
    "/whitelist_dominios.inc",
    methods=["GET", "HEAD"],
    response_class=PlainTextResponse,
    summary="Mapa Rspamd: dominios (filter=email:domain)",
)
async def whitelist_domains_inc(
    request: Request,
    token: str | None = Query(default=None),
) -> Response:
    """
    Una línea = un dominio (sin @). Para bloque multimap::

        type = \"from\";
        filter = \"email:domain\";
        map = \"https://HOST/security/whitelist_dominios.inc?token=...\";
    """
    _verify_feed_token(token)
    entries = _entries_from_env()
    body = render_rspamd_map(entries, kind=WhitelistEntryKind.domain, title="whitelist domains")
    return _plain_map_response(body, head_only=(request.method == "HEAD"))


@router.api_route(
    "/whitelist_correos.inc",
    methods=["GET", "HEAD"],
    response_class=PlainTextResponse,
    summary="Mapa Rspamd: correos completos (filter=email)",
)
async def whitelist_emails_inc(
    request: Request,
    token: str | None = Query(default=None),
) -> Response:
    _verify_feed_token(token)
    entries = _entries_from_env()
    body = render_rspamd_map(entries, kind=WhitelistEntryKind.email, title="whitelist emails")
    return _plain_map_response(body, head_only=(request.method == "HEAD"))


@router.get("/whitelist_preview", summary="Vista previa JSON (misma lista que los .inc)")
async def whitelist_preview(token: str | None = Query(default=None)) -> dict:
    """Útil para probar sin Mailcow: curl con el mismo ?token=."""
    _verify_feed_token(token)
    entries = _entries_from_env()
    domains, emails = split_entries(entries)
    settings = get_settings()
    host = (settings.domain_platform or "localhost").strip()
    base = f"https://{host}/security"
    base_api = f"https://{host}/api/security"
    tok_q = "?token=***" if token else ""
    return {
        "domains": domains,
        "emails": emails,
        "feed_urls": {
            "domains_inc": f"{base}/whitelist_dominios.inc{tok_q}",
            "emails_inc": f"{base}/whitelist_correos.inc{tok_q}",
            "domains_inc_via_api": f"{base_api}/whitelist_dominios.inc{tok_q}",
            "emails_inc_via_api": f"{base_api}/whitelist_correos.inc{tok_q}",
        },
        "entry_count": len(entries),
    }


@router.get("/normalize_test", summary="Probar normalización de una línea (PoC)")
async def normalize_test(
    q: str = Query(..., min_length=1, description="Ej: @dominio.com o user@dominio.com"),
    token: str | None = Query(default=None),
) -> dict:
    _verify_feed_token(token)
    try:
        ent = normalize_whitelist_input(q)
    except WhitelistNormalizeError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_entry", "message": str(exc), "raw": exc.raw},
        ) from exc
    return {
        "raw": ent.raw_input,
        "kind": ent.kind.value,
        "value": ent.value,
        "rspamd_line": ent.value,
        "map_file": "whitelist_dominios.inc" if ent.kind == WhitelistEntryKind.domain else "whitelist_correos.inc",
    }
