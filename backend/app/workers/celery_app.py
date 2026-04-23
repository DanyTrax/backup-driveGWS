"""Celery application configuration."""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "msa_backup",
    broker=settings.celery_broker_url or settings.redis_url + "/0",
    backend=settings.celery_result_backend or settings.redis_url + "/1",
    include=[
        "app.workers.tasks.backup_drive",
        "app.workers.tasks.backup_gmail",
        "app.workers.tasks.restore",
        "app.workers.tasks.maintenance",
        "app.workers.tasks.notify",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone=settings.tz,
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    result_expires=3600 * 24 * 7,
    task_default_queue="default",
)

celery_app.conf.beat_schedule = {
    "platform-backup-daily": {
        "task": "app.workers.tasks.maintenance.platform_backup_daily",
        "schedule": crontab(hour=settings.platform_backup_daily_hour, minute=0),
    },
    "directory-sync-hourly": {
        "task": "app.workers.tasks.maintenance.sync_directory",
        "schedule": crontab(minute=15),
    },
    "session-cleanup-daily": {
        "task": "app.workers.tasks.maintenance.cleanup_expired_sessions",
        "schedule": crontab(hour=2, minute=30),
    },
    "dispatch-scheduled-backups": {
        "task": "app.workers.tasks.maintenance.dispatch_scheduled_backups",
        "schedule": crontab(minute="*/5"),
    },
}
