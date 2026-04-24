"""Daily encrypted platform backup (Postgres dump + config).

Steps:
  1. `pg_dump -Fc` into /tmp.
  2. Bundle dump + /app/config + /var/msa/manifests into a .tar.gz.
  3. Encrypt the archive with `age` using the configured recipient.
  4. Upload to the vault Shared Drive through the Drive API.
  5. Enforce retention (N daily, N weekly, N monthly) by listing and trimming.
"""
from __future__ import annotations

import asyncio
import os
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

    root = await get_value(db, KEY_VAULT_ROOT_FOLDER_ID)
    drive_id = await get_value(db, KEY_VAULT_SHARED_DRIVE_ID)
    if not root:
        return {"ok": False, "error": "vault_root_missing"}

    dest_folder_id = await get_value(db, KEY_PLATFORM_BACKUP_DEST)
    if not dest_folder_id:
        folder = await ensure_folder(
            db, name="Platform-Backups", parent_id=root, drive_id=drive_id
        )
        dest_folder_id = folder["id"]
        await set_value(db, KEY_PLATFORM_BACKUP_DEST, dest_folder_id, category="platform_backup")
        await db.commit()

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with tempfile.TemporaryDirectory(prefix="msa_platform_", dir="/tmp") as tmp:
        workdir = Path(tmp)
        dump_path = workdir / "postgres.dump"
        await _pg_dump(dump_path)

        tar_path = workdir / f"msa-platform-{ts}.tar.gz"
        await asyncio.to_thread(
            _tarball,
            [dump_path, Path("/app/config"), Path("/var/msa/manifests")],
            tar_path,
        )

        age_path = workdir.parent / f"{tar_path.name}.age"
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
