# Restore playbook

Estrategias para recuperar datos desde la bóveda.

## 1) Restore de archivos de Drive

### Total (toda la carpeta del usuario)

- UI: **Usuarios** → usuario → pestaña **Drive** → **Restaurar total**.
- Opciones:
  - Destino: *Drive original* o *Carpeta nueva en Drive original* o *Descargar ZIP local*.
  - Fecha: por defecto último backup exitoso; podés elegir cualquiera del historial.
  - Sobrescribir colisiones: sí/no.
- Se añade etiqueta `Restaurado_YYYY-MM-DD` a la carpeta raíz.

### Selectivo

- Explorador de archivos con búsqueda por nombre/fecha/extensión.
- Seleccionás ítems sueltos → **Restaurar seleccionados** → mismas opciones de destino.

### Dry-run

- Antes de ejecutar, podés correr un **dry-run** que reporta:
  - N archivos a copiar
  - Tamaño total
  - Colisiones detectadas
  - Tiempo estimado

## 2) Restore de emails

### Desde Roundcube (granular, con 1 clic)

- El cliente (o el admin vía SSO) abre Roundcube con el webmail del backup.
- Botón **Restaurar al buzón original** en la toolbar. Acepta:
  - Un correo concreto
  - Varios seleccionados
  - Una carpeta entera
- Internamente la plataforma usa Gmail API + IMAP APPEND para escribir el mensaje en el Gmail original del usuario preservando fechas, remitente, etiquetas (labels) originales + label `Restaurado`.

### Desde la UI de la plataforma (bulk)

- **Usuarios** → usuario → pestaña **Correo** → **Restore en bloque**.
- Elegís fecha del backup y filtro (por etiqueta / por fecha / por remitente).
- La plataforma descomprime el `.mbox` y corre `gyb --action restore-mbox --label-restored`.

## 3) Restore de cuenta completa

- **Usuarios** → usuario → botón rojo **Restore total de cuenta**.
- Requiere confirmación con contraseña + MFA (si está habilitado).
- Ejecuta Drive total + Gmail total en paralelo.
- Ideal para recuperar una cuenta tras un incidente de ransomware.

## 4) Restore selectivo en Drive con `rclone`

Backend:

```bash
rclone copy \
  backup_vault:/MSA_Backups_Vault/user@dominio/drive/2026_04_20/root/proyectos/ \
  user_drive:/Restaurado_2026-04-22/proyectos/ \
  --progress --checksum
```

Ejecutado siempre dentro del contenedor `msa-backup-worker`, con los remotes generados dinámicamente desde la SA + DWD.

## 5) Trazabilidad

Cada restore genera:
- Entrada en `restore_jobs` con operador, destino, rango, estado.
- Entrada en `sys_audit`.
- Notificación opcional al cliente (toggle en tarea de restore).
