"""ORM models package.

Importing this package registers every SQLAlchemy model in ``Base.metadata``
so Alembic's autogenerate can see them and relationship strings resolve.
"""
from __future__ import annotations

from app.models.accounts import GwAccount, GwSyncLog
from app.models.audit import SysAudit
from app.models.base import Base
from app.models.mailbox_delegation import SysUserMailboxDelegation
from app.models.notifications import Notification, SysUserNotificationPref
from app.models.restore import RestoreJob
from app.models.settings import SysSetting
from app.models.tasks import BackupLog, BackupTask, backup_task_accounts
from app.models.users import SysPermission, SysRole, SysSession, SysUser, sys_role_permissions
from app.models.webmail import WebmailAccessToken

__all__ = [
    "Base",
    # users
    "SysUser",
    "SysRole",
    "SysPermission",
    "SysSession",
    "sys_role_permissions",
    # audit / settings
    "SysAudit",
    "SysSetting",
    # workspace accounts
    "GwAccount",
    "GwSyncLog",
    "SysUserMailboxDelegation",
    # tasks
    "BackupTask",
    "BackupLog",
    "backup_task_accounts",
    # restore
    "RestoreJob",
    # webmail
    "WebmailAccessToken",
    # notifications
    "Notification",
    "SysUserNotificationPref",
]
