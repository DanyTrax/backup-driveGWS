"""Progreso en vivo de backup Gmail: sondea disco (export GYB + import Maildir) mientras el worker copia."""
from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from pathlib import Path

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.enums import BackupStatus
from app.models.tasks import BackupLog
from app.services.progress_bus import publish
from app.utils.gmail_export_counts import count_gyb_export, count_maildir_messages

logger = logging.getLogger(__name__)

# Intervalo de sondeo (segundos) — visible en listado y detalle (messages / bytes / archivos).
GMAIL_BACKUP_PROGRESS_INTERVAL: float = 8.0


async def _merge_partial_progress(
    log_id: uuid.UUID,
    *,
    messages: int,
    bytes_count: int,
    files: int,
) -> None:
    """Actualiza contadores mientras el log siga ``running`` (sesión aislada)."""
    try:
        async with AsyncSessionLocal() as s:
            row = await s.execute(select(BackupLog).where(BackupLog.id == log_id))
            log = row.scalar_one_or_none()
            if log is None or log.status != BackupStatus.RUNNING.value:
                return
            log.messages_count = messages
            log.bytes_transferred = bytes_count
            log.files_count = files
            await s.commit()
    except Exception as exc:  # noqa: BLE001
        logger.debug("gmail progress merge skipped: %s", exc)


async def _sample_and_publish(
    log_id: uuid.UUID,
    log_id_str: str,
    sample_path: Path,
    mode: str,
) -> None:
    if mode == "gyb":
        msg, b, f = await asyncio.to_thread(count_gyb_export, sample_path)
        phase = "gyb"
    else:
        msg, b, f = await asyncio.to_thread(
            count_maildir_messages, sample_path
        )
        phase = "import_maildir"
    await _merge_partial_progress(
        log_id, messages=msg, bytes_count=b, files=f
    )
    await publish(
        log_id_str,
        {
            "stage": "gmail_progress",
            "phase": phase,
            "messages": msg,
            "bytes": b,
            "files": f,
        },
    )


async def _progress_loop(
    log_id: uuid.UUID,
    log_id_str: str,
    finished: asyncio.Event,
    sample_path: Path,
    mode: str,
) -> None:
    if not finished.is_set():
        try:
            await _sample_and_publish(
                log_id, log_id_str, sample_path, mode
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("gmail progress initial: %s", exc)
    while not finished.is_set():
        try:
            await asyncio.wait_for(
                finished.wait(), timeout=GMAIL_BACKUP_PROGRESS_INTERVAL
            )
        except asyncio.TimeoutError:
            pass
        else:
            # `finished` se disparó: salir del bucle.
            break
        if finished.is_set():
            break
        try:
            await _sample_and_publish(
                log_id, log_id_str, sample_path, mode
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("gmail progress tick: %s", exc)


def start_gmail_progress_ticker(
    log_id: uuid.UUID,
    log_id_str: str,
    path: Path,
    *,
    mode: str,
) -> tuple[asyncio.Event, asyncio.Task[None]]:
    """Arranca tarea de fondo; devuelve (evento para terminar, tarea)."""
    finished = asyncio.Event()

    async def _run() -> None:
        await _progress_loop(log_id, log_id_str, finished, path, mode)

    task = asyncio.create_task(_run(), name=f"gmail-progress-{log_id_str[:8]}")
    return finished, task


async def stop_gmail_progress_ticker(
    finished: asyncio.Event,
    task: asyncio.Task[None] | None,
) -> None:
    finished.set()
    if task is not None and not task.done():
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
