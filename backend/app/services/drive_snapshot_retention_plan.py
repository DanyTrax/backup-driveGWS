"""Lógica pura para elegir qué snapshots fechados eliminar (sin API ni ORM)."""
from __future__ import annotations


def folder_ids_to_prune(snapshot_folders: list[dict[str, str]], *, keep: int) -> list[str]:
    """Dado un listado de subcarpetas bajo MSA_Runs (cada una con ``id`` y ``name``), devuelve los
    ``id`` a borrar para dejar las ``keep`` más recientes según ``name`` (orden lexicográfico =
    cronológico para el prefijo ``YYYY-MM-DDTHH-MM``).
    """
    if keep <= 0 or len(snapshot_folders) <= keep:
        return []
    sorted_children = sorted(snapshot_folders, key=lambda x: x["name"], reverse=True)
    return [f["id"] for f in sorted_children[keep:]]
