"""Texto legible del último evento de progreso (para persistir en logs exitosos)."""
from __future__ import annotations

from typing import Any


def format_completion_summary_from_event(event: dict[str, Any] | None) -> str | None:
    """Resume el cierre del pipeline a partir del último evento Redis (si existe)."""
    if not event or not isinstance(event, dict):
        return None

    stage = str(event.get("stage") or "").strip()
    if not stage:
        return None

    if stage == "vault_zip_done":
        vr = str(event.get("vault_rel_zip") or "").strip()
        return f"Sellado ZIP al vault completado{f': {vr}' if vr else ''}."

    if stage == "vault_zip_skipped":
        reason = str(event.get("reason") or "sin motivo").strip()
        return f"GYB OK; subida ZIP omitida en esta corrida ({reason})."

    if stage == "vault_push" and event.get("ok") is True:
        purged = event.get("workdir_purged") is True
        sub = str(event.get("subpath") or "1-GMAIL/gyb_mbox").strip()
        tail = " Workdir GYB vaciado tras verificación." if purged else ""
        return f"Subida al vault ({sub}) completada.{tail}"

    if stage == "vault_closing":
        detail = str(event.get("detail_es") or "").strip()
        return detail or "Cierre del job Gmail (informe en vault si aplica)."

    if stage == "done" and str(event.get("status") or "") == "success":
        msgs = event.get("messages")
        if isinstance(msgs, int):
            return f"Job Gmail finalizado OK (~{msgs} mensajes en contador)."
        return "Job Gmail finalizado OK."

    if stage == "gyb_reseed_from_seal":
        search = str(event.get("search") or "").strip()
        return f"GYB incremental tras workdir vacío (filtro Gmail: {search or '—'})."

    if stage == "gyb_done":
        skip = event.get("gmail_skip_maildir_import") is True
        return "Export GYB en servidor listo" + (" (sin import Maildir)." if skip else ".")

    if stage == "vault_zip_built":
        zb = str(event.get("zip_basename") or "…").strip()
        n = event.get("files_in_zip")
        n_txt = str(n) if isinstance(n, int) else "—"
        return f"ZIP local generado ({zb}, {n_txt} archivos); subida al vault en curso o pendiente."

    if stage == "progress":
        phase = str(event.get("phase") or "").strip()
        if phase == "vault_zip_upload":
            return "Subida ZIP al vault en curso al cerrar el panel (revisá de nuevo al terminar)."
        if phase == "vault_zip_compress":
            return "Compresión ZIP en curso al cerrar el panel (revisá de nuevo al terminar)."

    if stage == "failed":
        err = str(event.get("error") or event.get("detail") or "").strip()
        return f"Job falló: {err}" if err else "Job falló."

    return f"Última fase registrada: {stage}."
