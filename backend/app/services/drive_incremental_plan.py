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
        * Tras esta corrida habrá ``n+1`` carpetas; si ``keep > 0``, se podarían las más antiguas.
          Si **alguna** carpeta a podar está marcada como ``(TOTAL)`` o ``(SNAPSHOT)``, esta corrida
          debe ser **full** para crear un nuevo ancla (la retención borró el tope de la cadena).
        * En régimen estable (solo se pisan ``(INC)`` viejos), esta corrida es **incremental** respecto
          a la carpeta **más reciente** por nombre.
        * Carpeta sin sufijos (migración): la poda no ve ``TOTAL`` en el nombre; no se fuerza full por
          retención salvo que borres manualmente un ancla renombrado.
    """
    sorted_asc = sorted(snapshot_children, key=lambda x: x["name"])
    sorted_desc = list(reversed(sorted_asc))
    n = len(sorted_asc)
    if n == 0:
        return "full", None

    prune_n = max(0, n + 1 - keep) if keep > 0 else 0
    would_remove = sorted_asc[:prune_n] if prune_n else []
    # Solo nueva copia TOTAL si la poda tocaría un ancla explícito; si solo caen (INC), sigue la cadena.
    drops_total_anchor = bool(would_remove) and any(
        is_full_snapshot_folder_name(x["name"]) for x in would_remove
    )

    if drops_total_anchor:
        return "full", None

    newest_name = sorted_desc[0]["name"]
    return "incremental", newest_name
