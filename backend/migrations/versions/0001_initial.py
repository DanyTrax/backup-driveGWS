"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-22 22:00:00

Creates every table and Postgres ENUM type used by the application.

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# -------------------------------------------------------------------- enums --
ENUMS: list[tuple[str, list[str]]] = [
    ("user_role", ["super_admin", "operator", "auditor"]),
    ("user_status", ["active", "suspended", "pending_verification"]),
    ("account_auth_method", ["service_account_dwd", "oauth_user"]),
    (
        "account_status",
        ["discovered", "approved", "suspended_in_workspace", "deleted_in_workspace"],
    ),
    ("backup_scope", ["drive_root", "drive_computadoras", "gmail", "full"]),
    ("backup_mode", ["full", "incremental", "mirror"]),
    (
        "backup_status",
        ["pending", "queued", "running", "paused", "success", "failed", "cancelled", "partial"],
    ),
    ("schedule_kind", ["daily", "weekly", "custom_cron", "manual"]),
    (
        "restore_scope",
        ["drive_total", "drive_selective", "gmail_mbox_bulk", "gmail_message", "full_account"],
    ),
    ("restore_status", ["pending", "running", "success", "failed", "cancelled"]),
    (
        "notification_channel",
        ["in_app", "toast", "modal", "banner", "telegram", "gmail", "discord", "web_push"],
    ),
    ("notification_severity", ["info", "success", "warning", "error", "critical"]),
    ("webmail_token_purpose", ["first_setup", "password_reset", "admin_sso", "client_sso"]),
    (
        "audit_action",
        [
            "login", "login_failed", "logout", "mfa_setup", "mfa_verified",
            "user_created", "user_updated", "user_deleted", "role_changed",
            "account_approved", "account_revoked",
            "backup_triggered", "backup_cancelled",
            "restore_triggered", "setting_changed", "webmail_accessed",
            "platform_backup", "git_refresh",
        ],
    ),
]


def _pg(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(name=name, create_type=False)


def upgrade() -> None:
    bind = op.get_bind()

    # Create ENUM types first.
    for name, values in ENUMS:
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)

    # ------------------------------------------------------------ sys_roles --
    op.create_table(
        "sys_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("description", sa.String(255)),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("code", name="uq_sys_roles_code"),
    )

    # ---------------------------------------------------------- sys_permissions --
    op.create_table(
        "sys_permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("module", sa.String(32), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("description", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("code", name="uq_sys_permissions_code"),
        sa.UniqueConstraint("module", "action", name="uq_sys_permissions_module_action"),
    )
    op.create_index("ix_sys_permissions_module", "sys_permissions", ["module"])

    # -------------------------------------------- sys_role_permissions (M2M) --
    op.create_table(
        "sys_role_permissions",
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("permission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("role_id", "permission_id", name="pk_sys_role_permissions"),
        sa.ForeignKeyConstraint(
            ["role_id"], ["sys_roles.id"],
            name="fk_sys_role_permissions_role_id_sys_roles", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["permission_id"], ["sys_permissions.id"],
            name="fk_sys_role_permissions_permission_id_sys_permissions", ondelete="CASCADE",
        ),
    )

    # ------------------------------------------------------------ sys_users --
    op.create_table(
        "sys_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", _pg("user_status"), nullable=False, server_default="active"),
        sa.Column("role_code", _pg("user_role"), nullable=False, server_default="auditor"),
        sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("mfa_secret_encrypted", sa.String(512)),
        sa.Column("mfa_backup_codes_encrypted", sa.String(2048)),
        sa.Column("mfa_enrolled_at", sa.DateTime(timezone=True)),
        sa.Column("failed_login_count", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column("last_login_ip", postgresql.INET()),
        sa.Column("password_changed_at", sa.DateTime(timezone=True)),
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("preferred_locale", sa.String(8), nullable=False, server_default="es"),
        sa.Column("preferred_timezone", sa.String(48), nullable=False, server_default="America/Bogota"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("email", name="uq_sys_users_email"),
        sa.ForeignKeyConstraint(
            ["role_id"], ["sys_roles.id"],
            name="fk_sys_users_role_id_sys_roles", ondelete="RESTRICT",
        ),
        sa.CheckConstraint("failed_login_count >= 0", name="ck_sys_users_failed_login_count_non_negative"),
    )
    op.create_index("ix_sys_users_email", "sys_users", ["email"])
    op.create_index("ix_sys_users_role_id", "sys_users", ["role_id"])
    op.create_index("ix_sys_users_status", "sys_users", ["status"])

    # --------------------------------------------------------- sys_sessions --
    op.create_table(
        "sys_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("jti", sa.String(64), nullable=False),
        sa.Column("refresh_token_hash", sa.String(128), nullable=False),
        sa.Column("user_agent", sa.String(400)),
        sa.Column("ip_address", postgresql.INET()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("jti", name="uq_sys_sessions_jti"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["sys_users.id"],
            name="fk_sys_sessions_user_id_sys_users", ondelete="CASCADE",
        ),
    )
    op.create_index("ix_sys_sessions_user_id", "sys_sessions", ["user_id"])
    op.create_index("ix_sys_sessions_jti", "sys_sessions", ["jti"])
    op.create_index("ix_sys_sessions_expires_at", "sys_sessions", ["expires_at"])
    op.create_index("ix_sys_sessions_user_revoked", "sys_sessions", ["user_id", "revoked_at"])

    # ------------------------------------------------------------ sys_audit --
    op.create_table(
        "sys_audit",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("actor_label", sa.String(255)),
        sa.Column("action", _pg("audit_action"), nullable=False),
        sa.Column("target_table", sa.String(64)),
        sa.Column("target_id", sa.String(128)),
        sa.Column("ip_address", postgresql.INET()),
        sa.Column("user_agent", sa.String(400)),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("message", sa.Text()),
        sa.Column("metadata_json", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["sys_users.id"],
            name="fk_sys_audit_actor_user_id_sys_users", ondelete="SET NULL",
        ),
    )
    op.create_index("ix_sys_audit_actor_user_id", "sys_audit", ["actor_user_id"])
    op.create_index("ix_sys_audit_action", "sys_audit", ["action"])
    op.create_index("ix_sys_audit_target_table", "sys_audit", ["target_table"])
    op.create_index("ix_sys_audit_target_id", "sys_audit", ["target_id"])
    op.create_index("ix_sys_audit_created_at_desc", "sys_audit", ["created_at"])
    op.create_index("ix_sys_audit_actor_action", "sys_audit", ["actor_user_id", "action"])

    # -------------------------------------------------------- sys_settings --
    op.create_table(
        "sys_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("value", sa.Text()),
        sa.Column("is_secret", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("category", sa.String(32), nullable=False, server_default="general"),
        sa.Column("description", sa.String(400)),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("key", name="uq_sys_settings_key"),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"], ["sys_users.id"],
            name="fk_sys_settings_updated_by_user_id_sys_users", ondelete="SET NULL",
        ),
    )
    op.create_index("ix_sys_settings_key", "sys_settings", ["key"])
    op.create_index("ix_sys_settings_category", "sys_settings", ["category"])

    # -------------------------------------------------------- gw_accounts --
    op.create_table(
        "gw_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("google_user_id", sa.String(64)),
        sa.Column("full_name", sa.String(160)),
        sa.Column("given_name", sa.String(80)),
        sa.Column("family_name", sa.String(80)),
        sa.Column("org_unit_path", sa.String(255)),
        sa.Column("is_workspace_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("workspace_status", _pg("account_status"), nullable=False, server_default="discovered"),
        sa.Column("is_backup_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("backup_enabled_at", sa.DateTime(timezone=True)),
        sa.Column("backup_enabled_by", postgresql.UUID(as_uuid=True)),
        sa.Column("exclusion_reason", sa.String(255)),
        sa.Column("discovered_at", sa.DateTime(timezone=True)),
        sa.Column("auth_method", _pg("account_auth_method"), nullable=False, server_default="service_account_dwd"),
        sa.Column("encrypted_refresh_token", sa.Text()),
        sa.Column("delegated_subject", sa.String(255)),
        sa.Column("imap_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("imap_password_hash", sa.String(255)),
        sa.Column("imap_password_set_at", sa.DateTime(timezone=True)),
        sa.Column("imap_last_login_at", sa.DateTime(timezone=True)),
        sa.Column("imap_last_login_ip", postgresql.INET()),
        sa.Column("imap_failed_attempts", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("imap_locked_until", sa.DateTime(timezone=True)),
        sa.Column("maildir_path", sa.String(500)),
        sa.Column("drive_vault_folder_id", sa.String(128)),
        sa.Column("last_sync_at", sa.DateTime(timezone=True)),
        sa.Column("last_successful_backup_at", sa.DateTime(timezone=True)),
        sa.Column("total_bytes_cache", sa.Integer()),
        sa.Column("total_messages_cache", sa.Integer()),
        sa.Column("tags_json", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("email", name="uq_gw_accounts_email"),
        sa.UniqueConstraint("google_user_id", name="uq_gw_accounts_google_user_id"),
        sa.ForeignKeyConstraint(
            ["backup_enabled_by"], ["sys_users.id"],
            name="fk_gw_accounts_backup_enabled_by_sys_users", ondelete="SET NULL",
        ),
    )
    op.create_index("ix_gw_accounts_email", "gw_accounts", ["email"])
    op.create_index("ix_gw_accounts_org_unit_path", "gw_accounts", ["org_unit_path"])
    op.create_index("ix_gw_accounts_is_backup_enabled", "gw_accounts", ["is_backup_enabled"])
    op.create_index("ix_gw_accounts_org_enabled", "gw_accounts", ["org_unit_path", "is_backup_enabled"])

    # -------------------------------------------------------- gw_sync_log --
    op.create_table(
        "gw_sync_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("triggered_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("ok", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("accounts_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accounts_new", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accounts_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accounts_suspended", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accounts_deleted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text()),
        sa.Column("raw_diff_json", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["triggered_by_user_id"], ["sys_users.id"],
            name="fk_gw_sync_log_triggered_by_user_id_sys_users", ondelete="SET NULL",
        ),
    )

    # --------------------------------------------------------- backup_tasks --
    op.create_table(
        "backup_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(400)),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("scope", _pg("backup_scope"), nullable=False),
        sa.Column("mode", _pg("backup_mode"), nullable=False, server_default="incremental"),
        sa.Column("schedule_kind", _pg("schedule_kind"), nullable=False, server_default="daily"),
        sa.Column("cron_expression", sa.String(64)),
        sa.Column("run_at_hour", sa.SmallInteger()),
        sa.Column("run_at_minute", sa.SmallInteger()),
        sa.Column("timezone", sa.String(48), nullable=False, server_default="America/Bogota"),
        sa.Column("retention_policy_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("filters_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("notify_channels_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("checksum_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("max_parallel_accounts", sa.SmallInteger(), nullable=False, server_default="2"),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("last_status", _pg("backup_status")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["sys_users.id"],
            name="fk_backup_tasks_created_by_user_id_sys_users", ondelete="SET NULL",
        ),
    )
    op.create_index("ix_backup_tasks_is_enabled", "backup_tasks", ["is_enabled"])

    # --------------------------------------------- backup_task_accounts (M2M) --
    op.create_table(
        "backup_task_accounts",
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("task_id", "account_id", name="pk_backup_task_accounts"),
        sa.ForeignKeyConstraint(
            ["task_id"], ["backup_tasks.id"],
            name="fk_backup_task_accounts_task_id_backup_tasks", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["gw_accounts.id"],
            name="fk_backup_task_accounts_account_id_gw_accounts", ondelete="CASCADE",
        ),
    )

    # --------------------------------------------------------- backup_logs --
    op.create_table(
        "backup_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_log_id", postgresql.UUID(as_uuid=True)),
        sa.Column("status", _pg("backup_status"), nullable=False, server_default="pending"),
        sa.Column("scope", _pg("backup_scope"), nullable=False),
        sa.Column("mode", _pg("backup_mode"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("pid", sa.Integer()),
        sa.Column("rclone_rc_port", sa.Integer()),
        sa.Column("rclone_job_id", sa.String(64)),
        sa.Column("celery_task_id", sa.String(64)),
        sa.Column("bytes_transferred", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("files_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("messages_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sha256_manifest_path", sa.String(500)),
        sa.Column("destination_path", sa.String(500)),
        sa.Column("error_summary", sa.Text()),
        sa.Column("detail_log_path", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["task_id"], ["backup_tasks.id"],
            name="fk_backup_logs_task_id_backup_tasks", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["gw_accounts.id"],
            name="fk_backup_logs_account_id_gw_accounts", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_log_id"], ["backup_logs.id"],
            name="fk_backup_logs_parent_log_id_backup_logs", ondelete="SET NULL",
        ),
    )
    op.create_index("ix_backup_logs_task_id", "backup_logs", ["task_id"])
    op.create_index("ix_backup_logs_account_id", "backup_logs", ["account_id"])
    op.create_index("ix_backup_logs_status", "backup_logs", ["status"])
    op.create_index("ix_backup_logs_celery_task_id", "backup_logs", ["celery_task_id"])
    op.create_index("ix_backup_logs_status_started", "backup_logs", ["status", "started_at"])
    op.create_index("ix_backup_logs_account_started", "backup_logs", ["account_id", "started_at"])

    # --------------------------------------------------------- restore_jobs --
    op.create_table(
        "restore_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("target_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_backup_log_id", postgresql.UUID(as_uuid=True)),
        sa.Column("scope", _pg("restore_scope"), nullable=False),
        sa.Column("status", _pg("restore_status"), nullable=False, server_default="pending"),
        sa.Column("selection_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("destination_kind", sa.String(32), nullable=False, server_default="original"),
        sa.Column("destination_details_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notify_client", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("preserve_original_dates", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("apply_restored_label", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("celery_task_id", sa.String(64)),
        sa.Column("items_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_restored", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bytes_restored", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("error_summary", sa.Text()),
        sa.Column("detail_log_path", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"], ["sys_users.id"],
            name="fk_restore_jobs_requested_by_user_id_sys_users", ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["target_account_id"], ["gw_accounts.id"],
            name="fk_restore_jobs_target_account_id_gw_accounts", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_backup_log_id"], ["backup_logs.id"],
            name="fk_restore_jobs_source_backup_log_id_backup_logs", ondelete="SET NULL",
        ),
    )
    op.create_index("ix_restore_jobs_requested_by_user_id", "restore_jobs", ["requested_by_user_id"])
    op.create_index("ix_restore_jobs_target_account_id", "restore_jobs", ["target_account_id"])
    op.create_index("ix_restore_jobs_status", "restore_jobs", ["status"])
    op.create_index("ix_restore_jobs_status_started", "restore_jobs", ["status", "started_at"])

    # ------------------------------------------------- webmail_access_tokens --
    op.create_table(
        "webmail_access_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purpose", _pg("webmail_token_purpose"), nullable=False),
        sa.Column("token_hash", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("issued_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("consumer_ip", postgresql.INET()),
        sa.Column("consumer_user_agent", sa.String(400)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("token_hash", name="uq_webmail_access_tokens_token_hash"),
        sa.ForeignKeyConstraint(
            ["account_id"], ["gw_accounts.id"],
            name="fk_webmail_access_tokens_account_id_gw_accounts", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["issued_by_user_id"], ["sys_users.id"],
            name="fk_webmail_access_tokens_issued_by_user_id_sys_users", ondelete="SET NULL",
        ),
    )
    op.create_index("ix_webmail_access_tokens_account_id", "webmail_access_tokens", ["account_id"])
    op.create_index("ix_webmail_access_tokens_token_hash", "webmail_access_tokens", ["token_hash"])
    op.create_index("ix_webmail_access_tokens_expires_at", "webmail_access_tokens", ["expires_at"])
    op.create_index("ix_webmail_tokens_account_purpose", "webmail_access_tokens", ["account_id", "purpose"])

    # --------------------------------------------------------- notifications --
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("recipient_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(48), nullable=False),
        sa.Column("severity", _pg("notification_severity"), nullable=False, server_default="info"),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text()),
        sa.Column("action_url", sa.String(500)),
        sa.Column("metadata_json", postgresql.JSONB()),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("dismissed_at", sa.DateTime(timezone=True)),
        sa.Column("delivered_channels_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["recipient_user_id"], ["sys_users.id"],
            name="fk_notifications_recipient_user_id_sys_users", ondelete="CASCADE",
        ),
    )
    op.create_index("ix_notifications_recipient_user_id", "notifications", ["recipient_user_id"])
    op.create_index("ix_notifications_category", "notifications", ["category"])
    op.create_index("ix_notifications_recipient_created", "notifications", ["recipient_user_id", "created_at"])
    op.create_index("ix_notifications_recipient_unread", "notifications", ["recipient_user_id", "read_at"])

    # ----------------------------------------------- sys_user_notification_prefs --
    op.create_table(
        "sys_user_notification_prefs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channels_matrix_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("quiet_hours_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("digest_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("digest_frequency", sa.String(16), nullable=False, server_default="daily"),
        sa.Column("telegram_chat_id", sa.String(64)),
        sa.Column("discord_webhook_url", sa.String(400)),
        sa.Column("gmail_recipient", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", name="uq_sys_user_notification_prefs_user_id"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["sys_users.id"],
            name="fk_sys_user_notification_prefs_user_id_sys_users", ondelete="CASCADE",
        ),
    )
    op.create_index("ix_sys_user_notification_prefs_user_id", "sys_user_notification_prefs", ["user_id"])


def downgrade() -> None:
    bind = op.get_bind()

    # Drop tables in reverse dependency order.
    for table in [
        "sys_user_notification_prefs",
        "notifications",
        "webmail_access_tokens",
        "restore_jobs",
        "backup_logs",
        "backup_task_accounts",
        "backup_tasks",
        "gw_sync_log",
        "gw_accounts",
        "sys_settings",
        "sys_audit",
        "sys_sessions",
        "sys_users",
        "sys_role_permissions",
        "sys_permissions",
        "sys_roles",
    ]:
        op.drop_table(table)

    # Drop ENUM types.
    for name, _ in reversed(ENUMS):
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
