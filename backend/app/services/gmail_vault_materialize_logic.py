"""Lógica pura materialización vault ZIP (sin SQLAlchemy)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from app.services.gmail_vault_zip_layout import parse_zip_basename_period

_CAL_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")


@dataclass
class VaultZipIndexEntry:
    rel_path: str
    period_start: date
    period_end: date
    size: int


class GmailVaultMaterializeError(ValueError):
    pass


def resolve_materialize_window(
    mode: str,
    *,
    anchor_date: Optional[date],
    date_from: Optional[date],
    date_to: Optional[date],
    calendar_month: Optional[str],
) -> tuple[date, date]:
    if mode == "single_day":
        if anchor_date is None:
            raise GmailVaultMaterializeError("anchor_date_required")
        return anchor_date, anchor_date
    if mode == "date_range":
        if date_from is None or date_to is None:
            raise GmailVaultMaterializeError("date_from_and_date_to_required")
        if date_to < date_from:
            raise GmailVaultMaterializeError("date_range_inverted")
        return date_from, date_to
    if mode == "month":
        raw = (calendar_month or "").strip()
        m = _CAL_MONTH_RE.match(raw)
        if not m:
            raise GmailVaultMaterializeError("calendar_month_must_be_YYYY-MM")
        y, mo = int(m.group(1)), int(m.group(2))
        if mo < 1 or mo > 12:
            raise GmailVaultMaterializeError("invalid_month")
        d0 = date(y, mo, 1)
        if mo == 12:
            d1 = date(y, 12, 31)
        else:
            d1 = date(y, mo + 1, 1) - timedelta(days=1)
        return d0, d1
    if mode == "all":
        return date(2000, 1, 1), date(2100, 12, 31)
    raise GmailVaultMaterializeError(f"unknown_mode: {mode}")


def period_overlaps_window(p0: date, p1: date, w0: date, w1: date) -> bool:
    return p0 <= w1 and p1 >= w0


def parse_lsjson_zip_entries(stdout: str) -> list[VaultZipIndexEntry]:
    try:
        items = json.loads(stdout or "[]")
    except json.JSONDecodeError as exc:
        raise GmailVaultMaterializeError(f"invalid_lsjson: {exc}") from exc
    out: list[VaultZipIndexEntry] = []
    for it in items:
        if it.get("IsDir"):
            continue
        name = str(it.get("Name") or "")
        if not name.lower().endswith(".zip"):
            continue
        rel_path = str(it.get("Path") or "").replace("\\", "/").lstrip("/")
        if not rel_path or ".." in rel_path.split("/"):
            continue
        parsed = parse_zip_basename_period(name)
        if parsed is None:
            continue
        p0, p1 = parsed
        sz = int(it.get("Size") or 0)
        out.append(VaultZipIndexEntry(rel_path=rel_path, period_start=p0, period_end=p1, size=sz))
    return out


def select_zip_entries_for_window(
    entries: list[VaultZipIndexEntry],
    window_start: date,
    window_end: date,
) -> list[VaultZipIndexEntry]:
    return [
        e
        for e in entries
        if period_overlaps_window(e.period_start, e.period_end, window_start, window_end)
    ]


def _merge_tree_into(src: Path, dest: Path) -> None:
    """Copia ``src`` (árbol) sobre ``dest`` (fusiona directorios; archivos se sobrescriben)."""
    import shutil

    dest.mkdir(parents=True, exist_ok=True)
    if not src.is_dir():
        return
    for item in src.iterdir():
        target = dest / item.name
        if item.is_dir():
            _merge_tree_into(item, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


def merge_materialized_session_into_gyb_workdir(local_materialize_root: Path, gyb_work_root: Path) -> int:
    """Lleva el contenido de ``extracted/`` a la carpeta de trabajo GYB y borra ZIPs en ``staging/``.

    Cada subcarpeta bajo ``extracted/`` corresponde a un ZIP (estructura GYB export). Se fusionan en
    ``gyb_work_root``. Luego se eliminan ``staging/*.zip`` y el árbol ``extracted/``.

    Returns:
        Número de entradas (subárboles o ficheros sueltos) fusionadas desde ``extracted``.
    """
    import shutil

    extracted = local_materialize_root / "extracted"
    staging = local_materialize_root / "staging"
    if not extracted.is_dir():
        raise GmailVaultMaterializeError("materialize_no_extracted_dir")
    merged = 0
    for child in sorted(extracted.iterdir()):
        if child.is_dir():
            _merge_tree_into(child, gyb_work_root)
            merged += 1
        elif child.is_file():
            gyb_work_root.mkdir(parents=True, exist_ok=True)
            shutil.copy2(child, gyb_work_root / child.name)
            merged += 1
    if merged == 0:
        raise GmailVaultMaterializeError("materialize_extracted_empty")
    if staging.is_dir():
        for z in staging.glob("*.zip"):
            z.unlink(missing_ok=True)
    shutil.rmtree(extracted, ignore_errors=True)
    return merged
