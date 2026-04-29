"""Nombres de carpeta de respaldos «Computadoras» / «Computers» (Drive for desktop).

Lógica aislada sin imports del ORM para tests y reutilización."""
from __future__ import annotations

import unicodedata


def fold_display_name(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.casefold().strip()


_COMPUTERS_ROOT_EXACT_FOLDED: frozenset[str] = frozenset(
    fold_display_name(x)
    for x in (
        "Computers",
        "Computer",
        "My computers",
        "Other computers",
        "Computadoras",
        "Computadora",
        "Mis computadoras",
        "Otras computadoras",
        "Computadores",
        "Meus computadores",
        "Outros computadores",
        "Ordinateurs",
        "Mes ordinateurs",
        "Autres ordinateurs",
    )
)


def computers_name_priority(name: str) -> int:
    """Menor = preferido cuando hay varias carpetas candidatas."""
    f = fold_display_name(name)
    preferred = {
        fold_display_name("Computadoras"): 0,
        fold_display_name("Computers"): 0,
        fold_display_name("Mis computadoras"): 1,
        fold_display_name("My computers"): 1,
        fold_display_name("Otras computadoras"): 2,
        fold_display_name("Other computers"): 2,
    }
    return preferred.get(f, 5)


def is_computers_backup_root_folder_name(name: str) -> bool:
    """True si ``name`` parece la carpeta de copias de Drive for desktop (raíz de Mi unidad)."""
    f = fold_display_name(name)
    if f in _COMPUTERS_ROOT_EXACT_FOLDED:
        return True
    fam = f.split()
    if len(fam) > 4:
        return False
    computer_tokens = {
        "computadoras",
        "computadores",
        "computadora",
        "computers",
        "computer",
        "ordinateurs",
        "ordinateur",
    }
    possessive = {"mis", "my", "mes", "otras", "other", "outros", "meus", "autres"}
    if any(t in computer_tokens for t in fam) and (
        any(t in possessive for t in fam) or len(fam) <= 2
    ):
        return True
    return False
