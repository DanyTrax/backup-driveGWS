"""Root API router — gathers every sub-router."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import (
    accounts,
    admin,
    audit,
    auth,
    backup,
    health,
    mailbox,
    meta,
    notifications,
    restore,
    settings as settings_routes,
    setup,
    tasks,
    users,
    webmail,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router)
api_router.include_router(meta.router)
api_router.include_router(users.router)
api_router.include_router(audit.router)
api_router.include_router(setup.router)
api_router.include_router(accounts.router)
api_router.include_router(mailbox.router, prefix="/accounts")
api_router.include_router(tasks.router)
api_router.include_router(backup.router)
api_router.include_router(restore.router)
api_router.include_router(webmail.router)
api_router.include_router(notifications.router)
api_router.include_router(settings_routes.router)
api_router.include_router(admin.router)
