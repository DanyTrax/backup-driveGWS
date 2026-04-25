"""Conteo de archivos GYB/Maildir en disco (sin dependencias de ORM/Redis)."""
from __future__ import annotations

from pathlib import Path


def count_gyb_export(path: Path) -> tuple[int, int, int]:
    """(mensajes .eml, total_bytes, files) con ``.mbox`` en bytes/archivos añadidos."""
    n_eml = 0
    total_b = 0
    n_files = 0
    if not path.is_dir():
        return 0, 0, 0
    for p in path.rglob("*.eml"):
        if p.is_file():
            n_eml += 1
            sz = p.stat().st_size
            total_b += sz
            n_files += 1
    for p in path.rglob("*.mbox"):
        if p.is_file():
            n_files += 1
            total_b += p.stat().st_size
    return n_eml, total_b, n_files


def count_maildir_messages(path: Path) -> tuple[int, int, int]:
    """Archivos bajo ``cur/`` o ``new/``."""
    n = 0
    b = 0
    if not path.is_dir():
        return 0, 0, 0
    for p in path.rglob("*"):
        if p.is_file() and p.parent.name in ("cur", "new"):
            n += 1
            b += p.stat().st_size
    return n, b, n
