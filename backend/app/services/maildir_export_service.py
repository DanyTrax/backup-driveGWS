"""Exportar árbol Maildir como ZIP (copia del backup local en disco)."""
from __future__ import annotations

import os
import re
import tempfile
import zipfile
from pathlib import Path


class MaildirExportTooLarge(Exception):
    """El total de bytes del Maildir supera el límite configurado."""

    def __init__(self, *, would_total: int, limit: int) -> None:
        self.would_total = would_total
        self.limit = limit
        super().__init__("maildir_export_too_large")


def safe_maildir_zip_stem(email: str) -> str:
    raw = (email or "mailbox").strip().lower().replace("@", "_at_")
    stem = re.sub(r"[^a-z0-9._-]+", "_", raw).strip("._-") or "mailbox"
    return stem[:120]


def _unlink_quiet(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def build_maildir_zip_file(maildir_root: Path, *, max_total_bytes: int = 0) -> Path:
    """Genera un ZIP del contenido de ``maildir_root`` (típicamente ``.../Maildir``).

    - Omite symlinks (solo archivos regulares).
    - ``max_total_bytes`` 0 = sin tope; si > 0, aborta antes de superarlo (suma de tamaños sin compresión).
    - El llamador debe borrar el path devuelto tras servirlo (p. ej. BackgroundTask).
    """
    root = maildir_root.resolve()
    if not root.is_dir():
        raise FileNotFoundError("maildir_root_missing")

    fd, tmp_path = tempfile.mkstemp(suffix=".zip", prefix="msa_maildir_")
    os.close(fd)
    tmp = Path(tmp_path)
    accumulated = 0

    try:
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(root.rglob("*"), key=lambda p: str(p)):
                if not path.is_file():
                    continue
                if path.is_symlink():
                    continue
                try:
                    rel = path.relative_to(root)
                except ValueError:
                    continue
                try:
                    sz = path.stat().st_size
                except OSError:
                    continue
                if max_total_bytes and accumulated + sz > max_total_bytes:
                    raise MaildirExportTooLarge(would_total=accumulated + sz, limit=max_total_bytes)
                accumulated += sz
                zf.write(path, rel.as_posix())
    except MaildirExportTooLarge:
        _unlink_quiet(str(tmp))
        raise
    except Exception:
        _unlink_quiet(str(tmp))
        raise
    return tmp
