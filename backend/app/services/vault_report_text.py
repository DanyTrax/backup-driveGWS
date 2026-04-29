"""Texto del informe de backup (sin rclone ni modelos ORM cargados al importar)."""
from __future__ import annotations

from typing import Any


def build_success_report_text(
    *,
    task: Any,
    account: Any,
    log: Any,
    drive_rclone_dest_subpath: str | None = None,
) -> str:
    lines: list[str] = [
        "MSA Backup Commander — Informe de ejecución",
        "=" * 50,
        f"Cuenta: {account.email}",
        f"Tarea: {task.name} (id={task.id})",
        f"Ámbito (scope): {log.scope}  |  Modo: {log.mode}",
        f"Estado: {log.status}",
        f"Inicio (UTC): {log.started_at}",
        f"Fin (UTC): {log.finished_at}",
        f"ID del log: {log.id}",
        f"Lote (run_batch_id): {log.run_batch_id or '—'}",
        f"Celery task id: {log.celery_task_id or '—'}",
        "",
        "Totales registrados en la plataforma:",
        f"  Bytes: {log.bytes_transferred}",
        f"  Archivos: {log.files_count}",
        f"  Mensajes: {log.messages_count}",
        f"  Errores (contador): {log.errors_count}",
        "",
    ]
    if drive_rclone_dest_subpath:
        lines.append(f"Subpath en vault (backup de archivos Drive / rclone): {drive_rclone_dest_subpath}")
        lines.append("")
    if log.destination_path:
        lines.append(f"Ruta destino (servidor / Maildir): {log.destination_path}")
        lines.append("")
    if log.sha256_manifest_path:
        lines.append(f"Manifiesto SHA-256 (ruta en servidor): {log.sha256_manifest_path}")
        lines.append("")
    if log.gmail_maildir_ready_at or log.gmail_vault_completed_at:
        lines.append(f"Gmail — Maildir listo (UTC): {log.gmail_maildir_ready_at or '—'}")
        lines.append(f"Gmail — Vault 1-GMAIL completado (UTC): {log.gmail_vault_completed_at or '—'}")
        lines.append("")
    if (getattr(log, "error_summary", None) or "").strip():
        lines.append("Nota / resumen de error en BD (no esperado en éxito):")
        lines.append(str(log.error_summary).strip()[:8000])
        lines.append("")
    lines.append("— Fin del informe —")
    return "\n".join(lines)
