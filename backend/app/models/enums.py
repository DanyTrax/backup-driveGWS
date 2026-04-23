"""Enum types shared across models and schemas.

Exposed both as native Python ``Enum`` (for use in services/schemas) and as
native PostgreSQL enum types (for use in column definitions).
"""
from __future__ import annotations

import enum

from sqlalchemy.dialects.postgresql import ENUM


class UserRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    OPERATOR = "operator"
    AUDITOR = "auditor"


class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    PENDING_VERIFICATION = "pending_verification"


class AccountAuthMethod(str, enum.Enum):
    SERVICE_ACCOUNT_DWD = "service_account_dwd"
    OAUTH_USER = "oauth_user"


class AccountStatus(str, enum.Enum):
    DISCOVERED = "discovered"
    APPROVED = "approved"
    SUSPENDED_IN_WORKSPACE = "suspended_in_workspace"
    DELETED_IN_WORKSPACE = "deleted_in_workspace"


class BackupScope(str, enum.Enum):
    DRIVE_ROOT = "drive_root"
    DRIVE_COMPUTADORAS = "drive_computadoras"
    GMAIL = "gmail"
    FULL = "full"


class BackupMode(str, enum.Enum):
    FULL = "full"
    INCREMENTAL = "incremental"
    MIRROR = "mirror"


class BackupStatus(str, enum.Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PARTIAL = "partial"


class ScheduleKind(str, enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    CUSTOM_CRON = "custom_cron"
    MANUAL = "manual"


class RestoreScope(str, enum.Enum):
    DRIVE_TOTAL = "drive_total"
    DRIVE_SELECTIVE = "drive_selective"
    GMAIL_MBOX_BULK = "gmail_mbox_bulk"
    GMAIL_MESSAGE = "gmail_message"
    FULL_ACCOUNT = "full_account"


class RestoreStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class NotificationChannel(str, enum.Enum):
    IN_APP = "in_app"
    TOAST = "toast"
    MODAL = "modal"
    BANNER = "banner"
    TELEGRAM = "telegram"
    GMAIL = "gmail"
    DISCORD = "discord"
    WEB_PUSH = "web_push"


class NotificationSeverity(str, enum.Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class WebmailTokenPurpose(str, enum.Enum):
    FIRST_SETUP = "first_setup"
    PASSWORD_RESET = "password_reset"
    ADMIN_SSO = "admin_sso"
    CLIENT_SSO = "client_sso"


class AuditAction(str, enum.Enum):
    LOGIN = "login"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    MFA_SETUP = "mfa_setup"
    MFA_VERIFIED = "mfa_verified"
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    USER_DELETED = "user_deleted"
    ROLE_CHANGED = "role_changed"
    ACCOUNT_APPROVED = "account_approved"
    ACCOUNT_REVOKED = "account_revoked"
    BACKUP_TRIGGERED = "backup_triggered"
    BACKUP_CANCELLED = "backup_cancelled"
    RESTORE_TRIGGERED = "restore_triggered"
    SETTING_CHANGED = "setting_changed"
    WEBMAIL_ACCESSED = "webmail_accessed"
    PLATFORM_BACKUP = "platform_backup"
    GIT_REFRESH = "git_refresh"


# -----------------------------------------------------------------------------
# Postgres ENUM type factories — created once at migration time.
# Reusing `create_type=False` on columns prevents Alembic from re-creating them.
# -----------------------------------------------------------------------------
def _pg_enum(py_enum: type[enum.Enum], name: str) -> ENUM:
    return ENUM(
        py_enum,
        name=name,
        values_callable=lambda e: [m.value for m in e],
        create_type=False,
        native_enum=True,
        validate_strings=True,
    )


user_role_enum = _pg_enum(UserRole, "user_role")
user_status_enum = _pg_enum(UserStatus, "user_status")
account_auth_method_enum = _pg_enum(AccountAuthMethod, "account_auth_method")
account_status_enum = _pg_enum(AccountStatus, "account_status")
backup_scope_enum = _pg_enum(BackupScope, "backup_scope")
backup_mode_enum = _pg_enum(BackupMode, "backup_mode")
backup_status_enum = _pg_enum(BackupStatus, "backup_status")
schedule_kind_enum = _pg_enum(ScheduleKind, "schedule_kind")
restore_scope_enum = _pg_enum(RestoreScope, "restore_scope")
restore_status_enum = _pg_enum(RestoreStatus, "restore_status")
notification_channel_enum = _pg_enum(NotificationChannel, "notification_channel")
notification_severity_enum = _pg_enum(NotificationSeverity, "notification_severity")
webmail_token_purpose_enum = _pg_enum(WebmailTokenPurpose, "webmail_token_purpose")
audit_action_enum = _pg_enum(AuditAction, "audit_action")


ALL_PG_ENUMS = (
    user_role_enum,
    user_status_enum,
    account_auth_method_enum,
    account_status_enum,
    backup_scope_enum,
    backup_mode_enum,
    backup_status_enum,
    schedule_kind_enum,
    restore_scope_enum,
    restore_status_enum,
    notification_channel_enum,
    notification_severity_enum,
    webmail_token_purpose_enum,
    audit_action_enum,
)
