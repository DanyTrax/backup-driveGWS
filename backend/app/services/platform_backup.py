"""Daily encrypted platform backup (Postgres dump + config).

Steps:
  1. `pg_dump -Fc` into /tmp.
  2. Bundle dump + selected host paths into a .tar.gz (ver ``_backup_paths_for_tar``).
  3. Encrypt the archive with `age` using the configured recipient.
  4. Upload to the vault Shared Drive through the Drive API.
  5. Enforce retention (N daily) by listing and trimming.

La restauración del .age es manual: ``age -d``, ``tar xzf``, ``pg_restore`` (ver documentación de despliegue).
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from googleapiclient.http import MediaFileUpload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.google.drive import build_drive_service, ensure_folder
from app.services.settings_service import (
    KEY_PLATFORM_BACKUP_DEST,
    KEY_VAULT_ROOT_FOLDER_ID,
    KEY_VAULT_SHARED_DRIVE_ID,
    get_value,
    set_value,
)

settings = get_settings()


def _age_recipient_from_env(raw: str | None) -> str:
    """Primera línea no vacía que no sea comentario (age no acepta '#' en el valor)."""
    if not raw:
        return ""
    for line in raw.replace("\r\n", "\n").split("\n"):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        return s
    return ""


def _write_git_head(path: Path) -> bool:
    cfg = get_settings()
    wt = Path(cfg.git_working_tree)
    if not (wt / ".git").is_dir():
        return False
    proc = subprocess.run(
        ["git", "-C", str(wt), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return False
    path.write_text(proc.stdout.strip()[:128] + "\n", encoding="utf-8")
    return True


def _backup_paths_for_tar(workdir: Path, dump_path: Path) -> list[Path]:
    entries: list[tuple[str, Path]] = [("postgres_custom.dump", dump_path)]
    for label, p in (
        ("app_config", Path("/app/config")),
        ("msa_manifests", Path("/var/msa/manifests")),
        ("rclone_config", Path("/root/.config/rclone")),
    ):
        if p.exists():
            entries.append((label, p))
    git_file = workdir / "git_HEAD.txt"
    if _write_git_head(git_file):
        entries.append(("git_head", git_file))
    manifest = {
        "format": "msa_platform_backup_v1",
        "components": [{"role": k, "host_path": str(v)} for k, v in entries],
    }
    man_path = workdir / "msa_platform_backup_manifest.json"
    man_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    entries.append(("manifest", man_path))
    return [p for _, p in entries]


def _safe_upload_basename(filename: str) -> str:
    base = Path(filename).name.strip() or "respaldo.age"
    base = re.sub(r"[^a-zA-Z0-9._-]+", "_", base)[:180]
    if not base.lower().endswith(".age"):
        base = f"{base}.age"
    return base


PLATFORM_INCOMING_DIR = Path("/platform_backups/incoming")
MAX_MANUAL_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024


def ensure_platform_incoming_dir() -> Path:
    PLATFORM_INCOMING_DIR.mkdir(parents=True, exist_ok=True)
    return PLATFORM_INCOMING_DIR


async def _pg_dump(target: Path) -> None:
    env = os.environ.copy()
    env["PGPASSWORD"] = settings.postgres_password
    args = [
        "pg_dump",
        "-h", settings.postgres_host,
        "-p", str(settings.postgres_port),
        "-U", settings.postgres_user,
        "-d", settings.postgres_db,
        "-Fc",
        "-f", str(target),
    ]
    proc = await asyncio.to_thread(
        subprocess.run, args, env=env, check=False, capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise RuntimeError(f"pg_dump_failed: {proc.stderr[:1000]}")


def _tarball(paths: list[Path], output: Path) -> None:
    args = ["tar", "czf", str(output)]
    for p in paths:
        if p.exists():
            args.append(str(p))
    subprocess.run(args, check=True, capture_output=True)


def _age_encrypt(src: Path, dst: Path, recipient: str) -> None:
    proc = subprocess.run(
        ["age", "-r", recipient, "-o", str(dst), str(src)],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"age_encrypt_failed: {proc.stderr[:500]}")


async def _upload_to_drive(db: AsyncSession, *, filepath: Path, parent_id: str) -> str:
    service = await build_drive_service(db)

    def _op():
        media = MediaFileUpload(str(filepath), resumable=True, mimetype="application/octet-stream")
        body = {"name": filepath.name, "parents": [parent_id]}
        return (
            service.files()
            .create(body=body, media_body=media, supportsAllDrives=True, fields="id,name")
            .execute()
        )

    resp = await asyncio.to_thread(_op)
    return str(resp.get("id"))


async def _enforce_retention(
    db: AsyncSession, *, parent_id: str, keep_latest: int
) -> list[str]:
    service = await build_drive_service(db)

    def _op():
        resp = (
            service.files()
            .list(
                q=f"'{parent_id}' in parents and trashed = false",
                orderBy="createdTime desc",
                fields="files(id,name,createdTime)",
                pageSize=200,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
        )
        return resp.get("files", []) or []

    files = await asyncio.to_thread(_op)
    to_delete = files[keep_latest:]

    def _delete(fid: str) -> None:
        service.files().delete(fileId=fid, supportsAllDrives=True).execute()

    deleted: list[str] = []
    for f in to_delete:
        try:
            await asyncio.to_thread(_delete, f["id"])
            deleted.append(f["id"])
        except Exception:  # pragma: no cover
            continue
    return deleted


async def resolve_platform_backup_folder_id(
    db: AsyncSession,
) -> tuple[str | None, str | None]:
    """Devuelve (folder_id_de_platform_backups, código_error)."""
    root = await get_value(db, KEY_VAULT_ROOT_FOLDER_ID)
    drive_id = await get_value(db, KEY_VAULT_SHARED_DRIVE_ID)
    if not root:
        return None, "vault_root_missing"
    dest = await get_value(db, KEY_PLATFORM_BACKUP_DEST)
    if not dest:
        folder = await ensure_folder(
            db, name="Platform-Backups", parent_id=root, drive_id=drive_id
        )
        dest = folder["id"]
        await set_value(db, KEY_PLATFORM_BACKUP_DEST, dest, category="platform_backup")
        await db.commit()
    return dest, None


async def list_platform_backup_files(
    db: AsyncSession, *, parent_id: str, limit: int = 30
) -> list[dict[str, Any]]:
    service = await build_drive_service(db)
    lim = max(1, min(int(limit), 100))

    def _op():
        resp = (
            service.files()
            .list(
                q=f"'{parent_id}' in parents and trashed = false",
                orderBy="createdTime desc",
                fields="files(id,name,createdTime,mimeType)",
                pageSize=lim,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
        )
        return resp.get("files", []) or []

    raw = await asyncio.to_thread(_op)
    out: list[dict[str, Any]] = []
    for f in raw:
        if str(f.get("mimeType") or "") == "application/vnd.google-apps.folder":
            continue
        fid = str(f.get("id") or "").strip()
        if not fid:
            continue
        out.append(
            {
                "id": fid,
                "name": str(f.get("name") or ""),
                "created_time": str(f.get("createdTime") or "") or None,
            }
        )
    return out


async def get_platform_backup_context(db: AsyncSession) -> dict[str, Any]:
    from app.services.google.drive import check_shared_drive

    root = await get_value(db, KEY_VAULT_ROOT_FOLDER_ID)
    drive_id = await get_value(db, KEY_VAULT_SHARED_DRIVE_ID)
    dest_folder_id = await get_value(db, KEY_PLATFORM_BACKUP_DEST)
    drive_name = None
    if drive_id:
        chk = await check_shared_drive(db, drive_id)
        if chk.get("ok") and isinstance(chk.get("drive"), dict):
            drive_name = str(chk["drive"].get("name") or "") or None
    recent: list[dict[str, Any]] = []
    if dest_folder_id:
        recent = await list_platform_backup_files(db, parent_id=dest_folder_id, limit=30)
    summary = (
        "Volcado Postgres (-Fc), carpeta /app/config, /var/msa/manifests, rclone en /root/.config/rclone "
        "(si existe), archivo git_HEAD.txt si hay .git en GIT_WORKING_TREE, y manifiesto JSON. "
        "Cifrado con age (clave pública en PLATFORM_BACKUP_AGE_RECIPIENT). "
        "No incluye /app/secrets ni el repositorio completo: actualización de código vía Git en el host o Git refresh si montás .git."
    )
    return {
        "vault_configured": bool(root and drive_id),
        "shared_drive_id": drive_id,
        "shared_drive_name": drive_name,
        "vault_root_folder_id": root,
        "platform_backup_folder_id": dest_folder_id,
        "folder_url": (
            f"https://drive.google.com/drive/folders/{dest_folder_id}" if dest_folder_id else None
        ),
        "vault_root_url": f"https://drive.google.com/drive/folders/{root}" if root else None,
        "recent_backups": recent,
        "includes_summary": summary,
        "incoming_path_container": str(PLATFORM_INCOMING_DIR),
    }


async def ingest_manual_platform_backup(
    db: AsyncSession,
    *,
    source_file: Path,
    original_filename: str,
    upload_to_drive: bool,
) -> dict[str, Any]:
    ensure_platform_incoming_dir()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = PLATFORM_INCOMING_DIR / f"manual-{ts}-{_safe_upload_basename(original_filename)}"
    shutil.move(str(source_file), str(dest))
    out: dict[str, Any] = {"ok": True, "local_path": str(dest), "drive_file_id": None}
    if not upload_to_drive:
        return out
    folder_id, err = await resolve_platform_backup_folder_id(db)
    if err or not folder_id:
        out["ok"] = False
        out["error"] = err or "no_destination_folder"
        return out
    try:
        out["drive_file_id"] = await _upload_to_drive(db, filepath=dest, parent_id=folder_id)
    except Exception as exc:  # noqa: BLE001
        out["ok"] = False
        out["error"] = str(exc)[:800]
    return out


async def run_platform_backup(db: AsyncSession) -> dict[str, Any]:
    recipient = _age_recipient_from_env(settings.platform_backup_age_recipient)
    if not recipient:
        return {"ok": False, "error": "age_recipient_not_configured"}
    if not recipient.startswith("age1"):
        return {
            "ok": False,
            "error": "age_recipient_invalid",
            "reason": (
                "PLATFORM_BACKUP_AGE_RECIPIENT debe ser la clave pública (una línea age1…), "
                "no el texto de comentario del .env.example. Generá una con: age-keygen -y -o backup.pub"
            ),
        }

    dest_folder_id, err = await resolve_platform_backup_folder_id(db)
    if err:
        return {"ok": False, "error": err}

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with tempfile.TemporaryDirectory(prefix="msa_platform_", dir="/tmp") as tmp:
        workdir = Path(tmp)
        dump_path = workdir / "postgres.dump"
        await _pg_dump(dump_path)

        tar_path = workdir / f"msa-platform-{ts}.tar.gz"
        tar_paths = _backup_paths_for_tar(workdir, dump_path)
        await asyncio.to_thread(_tarball, tar_paths, tar_path)

        age_path = workdir / f"{tar_path.name}.age"
        await asyncio.to_thread(_age_encrypt, tar_path, age_path, recipient)

        file_id = await _upload_to_drive(db, filepath=age_path, parent_id=dest_folder_id)

    deleted = await _enforce_retention(
        db, parent_id=dest_folder_id, keep_latest=settings.platform_backup_retention_daily
    )
    return {
        "ok": True,
        "file_id": file_id,
        "filename": f"msa-platform-{ts}.tar.gz.age",
        "retention_deleted": deleted,
    }
