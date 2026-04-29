"""Texto del informe de backup exitoso (sin rclone)."""
from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.services.vault_report_text import build_success_report_text


def test_build_success_report_includes_account_task_and_drive_path() -> None:
    tid = uuid.uuid4()
    lid = uuid.uuid4()
    task = SimpleNamespace(name="Noches", id=tid, filters_json={})
    account = SimpleNamespace(email="user@dominio.test")
    log = SimpleNamespace(
        scope="drive_root",
        mode="incremental",
        status="success",
        started_at="2026-04-23T10:00:00+00:00",
        finished_at="2026-04-23T10:15:00+00:00",
        id=lid,
        run_batch_id=None,
        celery_task_id="celery-xyz",
        bytes_transferred=100,
        files_count=5,
        messages_count=0,
        errors_count=0,
        destination_path="/var/mail/…",
        sha256_manifest_path=None,
        error_summary=None,
        gmail_maildir_ready_at=None,
        gmail_vault_completed_at=None,
    )
    text = build_success_report_text(
        task=task,
        account=account,
        log=log,
        drive_rclone_dest_subpath="2-DRIVE/_sync",
    )
    assert "user@dominio.test" in text
    assert "Noches" in text
    assert str(tid) in text
    assert str(lid) in text
    assert "2-DRIVE/_sync" in text
    assert "drive_root" in text
    assert "success" in text
