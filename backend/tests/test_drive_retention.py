"""Retención de snapshots Drive: lógica pura (sin Google API ni ORM)."""
from __future__ import annotations

import sys
from pathlib import Path

# Permite `python -m pytest` desde la carpeta backend sin instalar el paquete.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.services.drive_snapshot_retention_plan import folder_ids_to_prune


def test_prune_empty_when_keep_zero() -> None:
    kids = [{"id": "a", "name": "2026-04-20T10-00"}]
    assert folder_ids_to_prune(kids, keep=0) == []


def test_prune_empty_when_at_limit() -> None:
    kids = [
        {"id": "a", "name": "2026-04-20T10-00"},
        {"id": "b", "name": "2026-04-21T10-00"},
    ]
    assert folder_ids_to_prune(kids, keep=2) == []


def test_prune_removes_only_oldest_when_keep_two_of_three() -> None:
    kids = [
        {"id": "old", "name": "2026-04-20T10-00"},
        {"id": "mid", "name": "2026-04-21T10-00"},
        {"id": "new", "name": "2026-04-22T10-00"},
    ]
    assert folder_ids_to_prune(kids, keep=2) == ["old"]


def test_prune_keeps_lexicographic_newest() -> None:
    """Mismo día, distinta hora: el nombre fechado ordena bien como string."""
    kids = [
        {"id": "early", "name": "2026-04-22T08-00"},
        {"id": "late", "name": "2026-04-22T18-00"},
    ]
    assert folder_ids_to_prune(kids, keep=1) == ["early"]
