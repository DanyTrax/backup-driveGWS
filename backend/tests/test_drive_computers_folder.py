"""Detección de nombres de carpeta «Computadoras» / «Computers» en la raíz de Mi unidad."""
from __future__ import annotations

from app.services.computers_folder_names import is_computers_backup_root_folder_name


def test_exact_locale_names() -> None:
    assert is_computers_backup_root_folder_name("Otras computadoras")
    assert is_computers_backup_root_folder_name("Computadoras")
    assert is_computers_backup_root_folder_name("Computers")
    assert is_computers_backup_root_folder_name("My computers")
    assert is_computers_backup_root_folder_name("Mes ordinateurs")


def test_rejects_unrelated() -> None:
    assert not is_computers_backup_root_folder_name("Proyecto 2025")
    assert not is_computers_backup_root_folder_name("Documentos")


def test_heuristic_mis_computadoras() -> None:
    assert is_computers_backup_root_folder_name("Mis computadoras corporativas")

