"""PDF export layout smoke tests."""
from datetime import datetime, timezone

from app.schemas.tasks import BackupLogOut
from app.services.backup_logs_pdf import _COL_W, _PAGE_USABLE_MM, render_backup_logs_pdf


def _sample() -> BackupLogOut:
    return BackupLogOut(
        id="11111111-1111-1111-1111-111111111111",
        task_id="22222222-2222-2222-2222-222222222222",
        account_id="33333333-3333-3333-3333-333333333333",
        task_name="Vault Drive PC Cuentas independientes",
        account_email="monica_mora@themsagroup.com",
        scope="drive",
        mode="incremental",
        status="success",
        started_at=datetime(2026, 8, 11, 3, 3, 52, tzinfo=timezone.utc),
        finished_at=datetime(2026, 8, 11, 3, 10, 0, tzinfo=timezone.utc),
        bytes_transferred=22_114_419_697,
        files_count=0,
        messages_count=46037,
        errors_count=24,
        run_batch_id="dee35050-aaaa-bbbb-cccc-dddddddddddd",
        celery_task_id=None,
        sha256_manifest_path=None,
        destination_path=None,
        error_summary="Copia Drive parcial con avisos",
    )


def test_col_widths_fit_landscape_page() -> None:
    assert abs(sum(_COL_W) - _PAGE_USABLE_MM) < 0.01


def test_render_backup_logs_pdf_bytes() -> None:
    data = render_backup_logs_pdf([_sample()], filter_note="estado=success")
    assert data.startswith(b"%PDF")
    assert len(data) > 200
