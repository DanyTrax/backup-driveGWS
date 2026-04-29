# Redis (SSO Webmail) y carpeta `1-GMAIL` en Drive

## A) Error: «AUTH … called without any password configured for the default user»

Ese texto lo devuelve **Redis** cuando el **cliente** (API Python / Celery) intenta autenticarse con contraseña y el servidor **no** tiene `requirepass` configurado.

- El mensaje de tostada **«Redis no respondió al emitir SSO»** aparece al usar **Roundcube → «Entrar como admin»** (SSO), que escribe tokens en Redis. **No** es el mismo flujo que **Cuentas → Ver correo** (visor Maildir del panel, que lee disco y no usa Redis para SSO).
- Si viste el error en la pantalla de cuentas, puede ser una notificación **previa** (Webmail) o otra pestaña abierta.

### Qué revisar

1. **Misma instancia y misma política de clave**
   - En `docker-compose`, el servicio `redis` debe usar `--requirepass ${REDIS_PASSWORD}` y en `.env` la misma `REDIS_PASSWORD` no vacía (como en `.env.example`).
   - Si usás un **Redis externo o sin contraseña**, dejá **`REDIS_PASSWORD` vacío** y ajustá `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` **sin** `:${PASSWORD}@`, y el comando del contenedor Redis **sin** `--requirepass`. Mezclar «app con clave» y «Redis sin clave» produce exactamente este error.

2. **`REDIS_HOST` en el contenedor `app`**
   - Debe ser el hostname del servicio Redis en la **red interna** (`redis` en el compose estándar, o el nombre que uses). Si la app apunta por error a otro puerto/host (p. ej. Redis del host sin auth), verás desajustes de AUTH.

3. **Roundcube**
   - `REDIS_HOST`, `REDIS_PORT` y `REDIS_PASSWORD` del contenedor Roundcube deben ser el **mismo** Redis que la app (misma contraseña). En el repo: `REDIS_HOST=msa-backup-redis` en `docker-compose.yml`.

Tras cambiar `.env`: reiniciá **`redis`**, **`app`**, **`worker`**, **`beat`** y **`roundcube`**.

---

## B) No aparece `1-GMAIL` en el vault de Drive tras backups

La ruta de diseño es: **`1-GMAIL/gyb_mbox`** bajo la carpeta de vault de la cuenta (`drive_vault_folder_id`), subida con **rclone** **después** de un backup **Gmail** exitoso (GYB + opcional import Maildir), solo si el push al vault está habilitado.

### Condiciones que deben cumplirse

1. **Tarea con Gmail**  
   Scope **`gmail`** o **`full`**. Una tarea solo **Drive** no crea `1-GMAIL`.

2. **`drive_vault_folder_id` en la cuenta**  
   Sin carpeta vault de Shared Drive asignada, el job falla con error tipo `missing_drive_vault_folder_id`.

3. **Push Gmail al vault no desactivado**  
   En `filters_json` de la tarea no debe figurar `vault_gmail_disable_push: true`. Con layout separado (por defecto), el push está **activo**.

4. **Ejecución correcta hasta `vault_push`**  
   Revisá el log de backup en **Logs**: si falló GYB, Maildir o `rclone` al subir, no se crea la rama en Drive.

5. **No confundir con Drive**  
   Carpetas **fecha** bajo `2-DRIVE/MSA_Runs/...` vienen de **tareas Drive** con `drive_layout: dated_run`. Gmail va a **`1-GMAIL/`**, no ahí.

### Comprobación rápida

- En la UI de logs, último run **Gmail** → estado **success** y sin error `vault_rclone` / `missing_vault_for_gmail_push`.
- En el Explorer de Drive del cliente, entrar a la carpeta cuya ID es `drive_vault_folder_id` y buscar **`1-GMAIL`**.
