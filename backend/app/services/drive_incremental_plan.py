"""Cadena incremental bajo ``MSA_Runs``: copia completa (TOTAL) + corridas (INC) con ``rclone --compare-dest``.

Sin tocar API de Google aquí: solo lógica pura sobre la lista de carpetas ya listadas.
"""
from __future__ import annotations


def is_full_snapshot_folder_name(name: str) -> bool:
    """Carpeta considerada copia / punto de ancla (convención de nombre en vault)."""
    u = name.upper()
    return "(TOTAL)" in u or "(SNAPSHOT)" in u


def plan_next_dated_backup(
    snapshot_children: list[dict[str, str]],
    *,
    keep: int,
) -> tuple[str, str | None]:
    """Decide la próxima corrida fechada en modo cadena.

    Returns:
        ``(run_kind, compare_folder_name | None)`` donde ``run_kind`` es ``full`` o ``incremental``,
        y ``compare_folder_name`` es el ``name`` de la carpeta más reciente existente bajo ``MSA_Runs``,
        usado para ``--compare-dest`` (solo si incremental).

    Reglas:
        * Sin snapshots → copia **full** (primera ejecución).
        * Tras esta corrida se añadirá una carpeta nueva; si ``keep > 0`` y hay que podar, las
          ``prune_n`` más antiguas se eliminarían. Si entre ellas está la **más antigua** de todo el
          set, la próxima corrida debe ser **full** de nuevo (nuevo ancla), alineado con retención.
        * Si no queda ninguna carpeta marcada como TOTAL/SNAPSHOT **y** hay al menos una carpeta,
          igualmente se permite incremental respecto a la más reciente (migración desde nombres
          viejos sin sufijo).
    """
    sorted_asc = sorted(snapshot_children, key=lambda x: x["name"])
    sorted_desc = list(reversed(sorted_asc))
    n = len(sorted_asc)
    if n == 0:
        return "full", None

    prune_n = max(0, n + 1 - keep) if keep > 0 else 0
    would_remove = sorted_asc[:prune_n] if prune_n else []
    oldest = sorted_asc[0]
    oldest_id = oldest.get("id")
    drops_oldest = bool(would_remove) and any(x.get("id") == oldest_id for x in would_remove)

    if drops_oldest:
        return "full", None

    newest_name = sorted_desc[0]["name"]
    return "incremental", newest_name
