# Guía A — Crear Service Account en Google Cloud

Objetivo: obtener un archivo JSON que la plataforma usará para autenticarse contra Drive y Gmail de las 16 cuentas del dominio Google Workspace sin necesitar OAuth por usuario.

## Pasos

1. Entrá a <https://console.cloud.google.com/> con el usuario admin del Workspace.
2. Creá (o seleccioná) un **proyecto** — p.ej. `msa-backup-commander`.
3. **APIs & Services** → **Library** → habilitá:
   - Admin SDK API
   - Google Drive API
   - Gmail API
4. **APIs & Services** → **Credentials** → **Create Credentials** → **Service Account**.
   - Nombre: `msa-backup-sa`
   - Description: `Backup orchestrator for MSA Backup Commander`
   - Skip role assignment (no necesita IAM del proyecto, solo DWD en Workspace).
5. En la SA creada → pestaña **Keys** → **Add Key** → **JSON** → descargá el archivo.
6. Copiá ese archivo al VPS, en `/opt/stacks/backup-stack/secrets/service-account.json` (la plataforma lo lee de ahí).
7. Anotá el **Unique ID** (Client ID) de la SA — lo necesitás para la guía B.

## Validación

En la pestaña *Installer* de la plataforma, pegá la ruta del JSON y hacé clic en **Validar**. La plataforma confirma que:

- El archivo se parsea como JSON.
- El `client_email` termina en `.iam.gserviceaccount.com`.
- Existe el campo `private_key`.
- El proyecto asociado existe (llamada de prueba a `projects.get`).
