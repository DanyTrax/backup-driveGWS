# Guía D — Selección de cuentas (opt-in)

Tras la guía B la plataforma ya puede listar las cuentas del dominio. En esta pantalla decidís cuáles entran al programa de backup.

## Comportamiento

- Todas las cuentas detectadas aparecen listadas con: nombre, email, OU, estado en Workspace, `is_backup_enabled = false`.
- Excluí por defecto a la cuenta admin (podés desmarcarla o activarla como cualquiera).
- Al marcar una cuenta y confirmar, la plataforma **inmediatamente**:
  1. Crea `MSA_Backups_Vault/<email>/drive/` y `MSA_Backups_Vault/<email>/gmail/` en la Shared Drive.
  2. Crea `/var/mail/vhosts/<dominio>/<usuario>/Maildir` con la estructura estándar `cur/new/tmp`.
  3. Inserta el registro en `gw_accounts` con `imap_enabled = false` (no hay password aún) y `is_backup_enabled = true`.
  4. **No** lanza backup todavía — lo hacés desde el módulo de tareas.

## Re-sincronización

La plataforma vuelve a pedirle a la Admin SDK la lista cada 24 h (o cuando pulsás **Sync ahora**) y:

- Marca como `suspended_in_workspace` las cuentas que desaparecen del dominio.
- Detecta cuentas nuevas y las deja en estado `is_backup_enabled = false, discovered_at = now`.
- Cambios de OU se reflejan en el campo `org_unit_path`.

Todos estos cambios quedan en el historial `gw_sync_log` y generan notificaciones según las preferencias del admin.
