"""Centralized configuration loaded from environment via Pydantic."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal
from urllib.parse import quote

from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "MSA Backup Commander"
    app_env: Literal["development", "production"] = "production"
    tz: str = Field(
        default="America/Bogota",
        description="IANA tz para carpetas MSA_Runs, hora en API (/api/health, logs) y Celery Beat (variable TZ).",
    )

    domain_platform: str = Field(
        default="",
        description=(
            "Host público del panel, API y SPA (sin https://; ej. sistembk.ejemplo.com). "
            "Incluye /webmail/assign-password. No es el host de Roundcube."
        ),
    )
    domain_webmail: str = Field(
        default="",
        description=(
            "Solo el host de Roundcube (ej. webmailbk.ejemplo.com). SSO/ rid apuntan aquí; no sirve "
            "para abrir el panel ni /api (eso va en domain_platform o la misma ruta con NPM)."
        ),
    )

    secret_key: str = Field(min_length=32)
    fernet_key: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_access_minutes: int = 15
    jwt_refresh_days: int = 7

    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    redis_host: str = "redis"
    redis_port: int = 6379
    redis_password: str = ""

    celery_broker_url: str = ""
    celery_result_backend: str = ""
    celery_concurrency: int = 2
    celery_backup_max_concurrent: int = 2

    dovecot_master_user: str = ""
    dovecot_master_password: str = ""

    log_level: str = "INFO"
    log_json: bool = True
    log_retention_days: int = 30

    rate_limit_login_per_minute: int = 5
    rate_limit_magic_link_per_hour: int = 3
    rate_limit_api_per_minute: int = 60

    feature_webmail_enabled: bool = True
    feature_mfa_required_for_superadmin: bool = False
    feature_web_push: bool = False

    git_refresh_mode: Literal["webhook", "bind_mount", "both"] = "webhook"
    git_repo_url: str = ""
    git_branch: str = "main"
    # Ruta con carpeta .git (solo bind-mount avanzado). La imagen estándar no incluye .git en /app.
    git_working_tree: str = "/app"

    platform_backup_age_recipient: str = ""
    platform_backup_daily_hour: int = 3
    platform_backup_retention_daily: int = 7
    platform_backup_retention_weekly: int = 4
    platform_backup_retention_monthly: int = 12

    rclone_rc_port_range_start: int = 5572
    rclone_rc_port_range_end: int = 5599
    rclone_bwlimit: str = ""
    # Solo ``rclone copy`` local → vault ``1-GMAIL/gyb_mbox`` (muchos .eml). Subir un poco más
    # el paralelismo suele acortar tiempos; si Drive responde 403/rate limit, bajá estos valores.
    rclone_gmail_vault_transfers: int = Field(default=16, ge=1, le=128)
    rclone_gmail_vault_checkers: int = Field(default=16, ge=1, le=128)
    # GYB --action estimate en «Comprobar acceso». 0 = sin límite (hasta que termine GYB).
    account_verify_gyb_timeout_seconds: int = 0
    # Export ZIP del Maildir desde el panel. 0 = sin límite de tamaño (proveedor/ops asume el riesgo).
    maildir_export_max_bytes: int = 0

    host_docker_control_enabled: bool = False
    host_stack_deploy_enabled: bool = False
    host_docker_socket_path: str = "/var/run/docker.sock"
    host_stack_mount_path: str = ""
    host_compose_project_subdir: str = "docker"
    host_compose_env_file: str = "../.env"
    host_git_path: str = ""
    # Imagen para ``docker run`` del despliegue en segundo plano (ej. ghcr.io/.../app:latest).
    host_stack_deploy_runner_image: str = ""

    @field_validator("account_verify_gyb_timeout_seconds", mode="before")
    @classmethod
    def _non_negative_verify_gyb_tmo(cls, v: object) -> int:
        if v is None:
            return 0
        n = int(v)
        return max(0, n)

    @field_validator(
        "host_docker_socket_path",
        "host_stack_mount_path",
        "host_git_path",
        "host_stack_deploy_runner_image",
        mode="before",
    )
    @classmethod
    def _strip_host_paths(cls, v: object) -> str:
        if v is None:
            return ""
        return str(v).strip()

    @field_validator("maildir_export_max_bytes", mode="before")
    @classmethod
    def _non_negative_maildir_export_max(cls, v: object) -> int:
        if v is None:
            return 0
        return max(0, int(v))

    @field_validator("rclone_bwlimit", mode="before")
    @classmethod
    def _clean_rclone_bwlimit(cls, v: object) -> str:
        """Evita que un .env tipo ``RCLONE_BWLIMIT=  # comentario`` rompa rclone (lee RCLONE_* del entorno)."""
        if v is None:
            return ""
        s = str(v).strip()
        if "#" in s:
            s = s.split("#", 1)[0].strip()
        if not s or s.startswith("#"):
            return ""
        return s

    @computed_field  # type: ignore[misc]
    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field  # type: ignore[misc]
    @property
    def database_url_async(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field  # type: ignore[misc]
    @property
    def redis_url(self) -> str:
        # Caracteres especiales en la contraseña rompen el URI si no se escapan (@, :, /, #, etc.).
        auth = (
            f":{quote(self.redis_password, safe='')}@"
            if self.redis_password
            else ""
        )
        return f"redis://{auth}{self.redis_host}:{self.redis_port}"

    @property
    def platform_public_origin(self) -> str:
        """Origen `https://...` de DOMAIN_PLATFORM: panel, `/api` y `/webmail/assign-password` (misma app)."""
        d = (self.domain_platform or "").strip()
        if not d:
            return ""
        if d.startswith("http://") or d.startswith("https://"):
            return d.rstrip("/")
        return f"https://{d.split('/')[0].strip()}"

    @property
    def webmail_public_origin(self) -> str:
        """Origen `https://...` de DOMAIN_WEBMAIL: solo Roundcube; URLs del plugin msa_sso (`rid=`, index.php)."""
        d = (self.domain_webmail or "").strip()
        if not d:
            return ""
        if d.startswith("http://") or d.startswith("https://"):
            return d.rstrip("/")
        return f"https://{d.split('/')[0].strip()}"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
