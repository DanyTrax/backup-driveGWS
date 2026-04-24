"""Constants for asyncio subprocess streams.

GYB y rclone pueden volcar progreso en una sola línea > 64 KiB; el límite por defecto
de ``StreamReader`` provoca ``LimitOverrunError`` / "Separator is not found, and chunk exceed the limit".
"""
from __future__ import annotations

# Límite del buffer interno de asyncio.StreamReader (no confundir con tamaño de línea leída).
SUBPROCESS_PIPE_LIMIT = 16 * 1024 * 1024
