"""GYB bajo ``1-GMAIL/gyb_mbox`` en el vault de cuenta (Google Drive vía rclone)."""
from __future__ import annotations

import json
import subprocess
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.services.gyb_work_browser_service import (
    GybEmlPage,
    GybEmlSummary,
    GybWorkFolder,
    decode_gyb_eml_relpath,
    encode_eml_rel_key,
    read_gyb_eml_leaf_bytes_from_bytes,
    read_gyb_eml_message_from_bytes,
    _eml_bytes_matches_search,
    _headers_from_eml_bytes,
)
from app.services.rclone_service import RcloneConfig, _subprocess_env_for_rclone
from app.services.vault_layout import gmail_vault_rclone_subpath


class RcloneVaultGybError(RuntimeError):
    pass


@dataclass(slots=True)
class _VaultEmlRow:
    rel: str
    size: int
    mtime_ns: int


_LSJSON_CACHE: dict[str, tuple[float, list[_VaultEmlRow]]] = {}
_CACHE_TTL_SEC = 90.0


def _lsjson_cache_key(account_id: uuid.UUID, vault_folder_id: str) -> str:
    return f"{account_id}:{vault_folder_id.strip()}"


def clear_gyb_vault_lsjson_cache_for_tests() -> None:
    _LSJSON_CACHE.clear()


def get_gyb_vault_eml_rows_cached(
    cfg: RcloneConfig,
    *,
    account_id: uuid.UUID,
    vault_folder_id: str,
) -> list[_VaultEmlRow]:
    key = _lsjson_cache_key(account_id, vault_folder_id)
    now = time.monotonic()
    hit = _LSJSON_CACHE.get(key)
    if hit and (now - hit[0]) < _CACHE_TTL_SEC:
        return hit[1]
    rows = rclone_lsjson_gyb_vault(cfg)
    _LSJSON_CACHE[key] = (now, rows)
    return rows


def _gyb_vault_remote_root() -> str:
    sub = gmail_vault_rclone_subpath().strip().strip("/")
    return f"dest:{sub}/"


def _safe_folder_id(folder_id: str) -> str:
    raw = (folder_id or "").strip().replace("\\", "/").strip("/")
    if ".." in raw.split("/"):
        raise ValueError("invalid_folder")
    return raw


def _rows_for_folder(
    all_rows: list[_VaultEmlRow], folder_id: str, list_scope: str
) -> list[_VaultEmlRow]:
    if list_scope == "all":
        return list(all_rows)
    fid = _safe_folder_id(folder_id)
    out: list[_VaultEmlRow] = []
    for r in all_rows:
        parent = str(Path(r.rel).parent.as_posix())
        if parent == ".":
            parent = ""
        if parent == fid:
            out.append(r)
    return out


def _parse_lsjson_modtime(s: str) -> int:
    s = (s or "").strip()
    if not s:
        return 0
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1_000_000_000)
    except (ValueError, TypeError, OSError, OverflowError):
        return 0


def rclone_lsjson_gyb_vault(cfg: RcloneConfig) -> list[_VaultEmlRow]:
    base = _gyb_vault_remote_root()
    argv = [
        "/usr/bin/rclone",
        "lsjson",
        base,
        "-R",
        "--config",
        cfg.config_path,
    ]
    proc = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=600,
        env=_subprocess_env_for_rclone(),
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "rclone_lsjson_failed")[:2000]
        raise RcloneVaultGybError(err)
    try:
        items = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise RcloneVaultGybError("invalid_lsjson") from exc
    rows: list[_VaultEmlRow] = []
    for it in items:
        if it.get("IsDir"):
            continue
        name = str(it.get("Name") or "")
        if not name.lower().endswith(".eml"):
            continue
        rel_path = str(it.get("Path") or "").replace("\\", "/").lstrip("/")
        if not rel_path or ".." in rel_path.split("/"):
            continue
        sz = int(it.get("Size") or 0)
        mt = _parse_lsjson_modtime(str(it.get("ModTime") or ""))
        rows.append(_VaultEmlRow(rel=rel_path, size=sz, mtime_ns=mt))
    return rows


def list_gyb_vault_work_folders(rows: list[_VaultEmlRow]) -> list[GybWorkFolder]:
    seen: set[str] = set()
    for row in rows:
        parent = str(Path(row.rel).parent.as_posix())
        if parent == ".":
            seen.add("")
        else:
            seen.add(parent)

    def sort_key(fid: str) -> tuple[int, str]:
        return (0 if fid == "" else 1, fid.lower())

    out: list[GybWorkFolder] = []
    for fid in sorted(seen, key=sort_key):
        name = "(raíz)" if fid == "" else fid.replace("/", " / ")
        out.append(GybWorkFolder(folder_id=fid, display_name=name))
    return out


def rclone_cat_gyb_vault_eml(
    cfg: RcloneConfig,
    rel_under_gyb: str,
    *,
    limit: int | None = None,
    timeout: int = 180,
) -> bytes:
    rel = rel_under_gyb.strip().replace("\\", "/").lstrip("/")
    if not rel or ".." in rel.split("/") or not rel.lower().endswith(".eml"):
        raise ValueError("invalid_eml_path")
    sub = gmail_vault_rclone_subpath().strip().strip("/")
    remote = f"dest:{sub}/{rel}"
    argv = ["/usr/bin/rclone", "cat", remote, "--config", cfg.config_path]
    env = _subprocess_env_for_rclone()
    if limit is not None and limit > 0:
        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        try:
            assert proc.stdout is not None
            data = proc.stdout.read(limit)
        finally:
            proc.kill()
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                pass
        return data if isinstance(data, bytes) else b""

    proc = subprocess.run(
        argv,
        capture_output=True,
        timeout=timeout,
        env=env,
    )
    if proc.returncode != 0:
        raise FileNotFoundError("eml_not_found")
    return proc.stdout if proc.stdout else b""


def list_gyb_vault_eml_summaries(
    cfg: RcloneConfig,
    *,
    all_rows: list[_VaultEmlRow],
    folder_id: str = "",
    limit: int = 80,
    offset: int = 0,
    q: str | None = None,
    list_scope: str = "folder",
    sort_by: str = "header_date",
    sort_order: str = "desc",
) -> GybEmlPage:
    # En Drive no hay mtime de archivo local; ``header_date`` del mensaje requeriría un ``cat``
    # por cada fila para ordenar todo el ámbito. Se ordena por ModTime remoto (lsjson) siempre.
    _ = sort_by
    try:
        scoped = _rows_for_folder(all_rows, folder_id, list_scope)
    except ValueError:
        return GybEmlPage(items=[], has_more=False, total_in_scope=0, total_matches=0)
    qn = (q or "").strip().lower()
    lim = max(1, min(limit, 200))
    off = max(0, offset)
    total_in_scope = len(scoped)
    if qn:
        matched: list[_VaultEmlRow] = []
        for row in scoped:
            try:
                chunk = rclone_cat_gyb_vault_eml(cfg, row.rel, limit=96_000)
            except FileNotFoundError:
                continue
            if _eml_bytes_matches_search(chunk, qn):
                matched.append(row)
        work = matched
        total_matches = len(matched)
    else:
        work = scoped
        total_matches = total_in_scope

    rev = sort_order != "asc"
    sorted_rows = sorted(work, key=lambda r: (r.mtime_ns, r.rel), reverse=rev)
    slice_rows = sorted_rows[off : off + lim]
    has_more = off + len(slice_rows) < total_matches
    items: list[GybEmlSummary] = []
    for row in slice_rows:
        k = encode_eml_rel_key(Path(row.rel))
        try:
            chunk = rclone_cat_gyb_vault_eml(cfg, row.rel, limit=96_000)
            subj, from_, date = _headers_from_eml_bytes(chunk)
        except (FileNotFoundError, OSError, ValueError):
            subj, from_, date = "(error al leer)", "—", None
        items.append(
            GybEmlSummary(
                key=k,
                subject=subj,
                from_addr=from_,
                date_display=date,
                size=row.size,
                labels=None,
            )
        )
    return GybEmlPage(
        items=items,
        has_more=has_more,
        total_in_scope=total_in_scope,
        total_matches=total_matches,
    )


def read_gyb_vault_eml_message(cfg: RcloneConfig, *, key: str):
    rel = decode_gyb_eml_relpath(key)
    raw = rclone_cat_gyb_vault_eml(cfg, rel, limit=None)
    return read_gyb_eml_message_from_bytes(raw, key=key)


def read_gyb_vault_eml_leaf(
    cfg: RcloneConfig, *, key: str, leaf_index: int
) -> tuple[bytes, str | None, str]:
    rel = decode_gyb_eml_relpath(key)
    raw = rclone_cat_gyb_vault_eml(cfg, rel, limit=None)
    return read_gyb_eml_leaf_bytes_from_bytes(raw, leaf_index=leaf_index)
