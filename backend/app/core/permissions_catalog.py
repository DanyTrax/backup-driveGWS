"""Canonical catalog of permissions and default role -> permission mapping.

Single source of truth used by:
  * the seed script (0002_seed data migration)
  * the backend RBAC middleware
  * the frontend (exported via GET /api/meta/permissions)
"""
from __future__ import annotations

from dataclasses import dataclass

from app.models.enums import UserRole


@dataclass(frozen=True, slots=True)
class PermissionSpec:
    module: str
    action: str
    description: str

    @property
    def code(self) -> str:
        return f"{self.module}.{self.action}"


# --------------------------------------------------------------- catalog ----
PERMISSIONS: tuple[PermissionSpec, ...] = (
    # --- sys_users ---
    PermissionSpec("users", "view", "Ver lista y detalle de usuarios de plataforma"),
    PermissionSpec("users", "create", "Crear usuarios de plataforma"),
    PermissionSpec("users", "edit", "Editar usuarios (rol, estado, preferencias)"),
    PermissionSpec("users", "delete", "Eliminar usuarios de plataforma"),
    PermissionSpec("users", "reset_password", "Forzar reset de contraseña"),
    # --- roles (roles personalizados en sys_roles) ---
    PermissionSpec("roles", "view", "Ver roles y los permisos asignados"),
    PermissionSpec("roles", "manage", "Crear, editar y eliminar roles personalizados"),
    # --- gw_accounts ---
    PermissionSpec("accounts", "view", "Ver cuentas de Workspace"),
    PermissionSpec("accounts", "approve", "Aprobar cuenta para backup (opt-in)"),
    PermissionSpec("accounts", "revoke", "Revocar backup de una cuenta"),
    PermissionSpec("accounts", "sync", "Disparar sincronización de Directorio"),
    PermissionSpec("accounts", "edit", "Editar metadatos y configuración de cuenta"),
    # --- backup tasks ---
    PermissionSpec("tasks", "view", "Ver definiciones de tareas de backup"),
    PermissionSpec("tasks", "create", "Crear nuevas tareas de backup"),
    PermissionSpec("tasks", "edit", "Editar tareas existentes"),
    PermissionSpec("tasks", "delete", "Eliminar tareas"),
    PermissionSpec("tasks", "run", "Lanzar, pausar, cancelar o reintentar tareas"),
    # --- backup logs ---
    PermissionSpec("logs", "view", "Ver historial de ejecuciones"),
    PermissionSpec("logs", "export", "Exportar historial (PDF u otros formatos)"),
    PermissionSpec("logs", "delete", "Eliminar registros del historial de ejecuciones"),
    # --- restores ---
    PermissionSpec("restore", "view", "Ver trabajos de restauración"),
    PermissionSpec("restore", "create", "Crear trabajos de restauración (Drive o Gmail)"),
    PermissionSpec("restore", "cancel", "Cancelar un trabajo de restauración en curso"),
    # --- webmail ---
    PermissionSpec("webmail", "sso_admin", "Acceder a cualquier buzón via SSO master"),
    PermissionSpec("webmail", "issue_magic_link", "Emitir magic link para un cliente"),
    PermissionSpec("webmail", "revoke_access", "Revocar acceso webmail de una cuenta"),
    # --- mailbox (visor Maildir en panel) ---
    PermissionSpec("mailbox", "view_all", "Ver correo (Maildir) de cualquier cuenta con backup"),
    PermissionSpec("mailbox", "view_delegated", "Ver correo solo en cuentas delegadas explícitamente"),
    PermissionSpec("mailbox", "delegate", "Asignar o quitar cuentas auditables (delegación Maildir)"),
    # --- bóveda Drive (Shared Drive / respaldos por cuenta) ---
    PermissionSpec(
        "vault_drive",
        "view_all",
        "Explorar la bóveda de respaldo en Drive de cualquier cuenta (árbol y búsqueda)",
    ),
    PermissionSpec(
        "vault_drive",
        "view_delegated",
        "Explorar la bóveda solo en cuentas delegadas explícitamente",
    ),
    PermissionSpec(
        "vault_drive",
        "delegate",
        "Asignar o quitar cuentas para el visor de bóveda Drive (delegación)",
    ),
    # --- settings / platform ---
    PermissionSpec("settings", "view", "Ver configuración del sistema"),
    PermissionSpec("settings", "edit", "Modificar configuración del sistema"),
    PermissionSpec("settings", "branding", "Cambiar branding (logo, colores, nombre, pie de página)"),
    PermissionSpec("platform", "refresh", "Ejecutar Git Refresh"),
    PermissionSpec("platform", "backup", "Ejecutar platform backup manualmente"),
    PermissionSpec(
        "platform",
        "host_docker",
        "Limpieza programada o manual de imágenes Docker en el host (containerd; requiere docker.sock)",
    ),
    PermissionSpec(
        "platform",
        "stack_deploy",
        "Actualizar la pila desde el panel (git pull / docker compose build; requiere montaje del repo + socket)",
    ),
    PermissionSpec(
        "platform",
        "purge_all_mail_local",
        "Eliminar todas las copias locales de correo de todas las cuentas (Maildir, GYB, logs Gmail BD, tokens webmail)",
    ),
    PermissionSpec(
        "accounts",
        "purge_mail_local",
        "Purgar datos locales de correo de una cuenta (selectivo) desde el panel",
    ),
    # --- audit ---
    PermissionSpec("audit", "view", "Leer el log de auditoría"),
    # --- notifications ---
    PermissionSpec("notifications", "manage_global", "Configurar canales globales de notificación"),
)


# Map: role_code -> set of permission codes
# Fuente única para el seed y para pruebas de autorización.
DEFAULT_ROLE_PERMISSIONS: dict[UserRole, frozenset[str]] = {
    UserRole.SUPER_ADMIN: frozenset(p.code for p in PERMISSIONS),
    UserRole.OPERATOR: frozenset(
        {
            "users.view",
            "users.create",
            "users.edit",
            "users.reset_password",
            "roles.view",
            "roles.manage",
            "accounts.view",
            "accounts.approve",
            "accounts.revoke",
            "accounts.sync",
            "accounts.edit",
            "accounts.purge_mail_local",
            "tasks.view", "tasks.create", "tasks.edit", "tasks.delete", "tasks.run",
            "logs.view", "logs.export", "logs.delete",
            "restore.view", "restore.create", "restore.cancel",
            "webmail.sso_admin", "webmail.issue_magic_link", "webmail.revoke_access",
            "mailbox.view_all", "mailbox.delegate",
            "vault_drive.view_all", "vault_drive.delegate",
            "settings.view",
            "settings.branding",
            "platform.refresh",
            "notifications.manage_global",
            "audit.view",
        }
    ),
    UserRole.AUDITOR: frozenset(
        {
            "users.view",
            "accounts.view",
            "tasks.view",
            "logs.view", "logs.export",
            "restore.view",
            "settings.view",
            "audit.view",
            "mailbox.view_delegated",
            "vault_drive.view_delegated",
        }
    ),
}


ROLE_DISPLAY: dict[UserRole, tuple[str, str]] = {
    UserRole.SUPER_ADMIN: ("Super Administrador", "Acceso completo incluido cambio de configuración crítica"),
    UserRole.OPERATOR: (
        "Operador",
        "Gestiona backups, restauraciones y cuentas; puede personalizar branding del panel (nombre, colores, logo).",
    ),
    UserRole.AUDITOR: ("Auditor", "Solo lectura del sistema"),
}
