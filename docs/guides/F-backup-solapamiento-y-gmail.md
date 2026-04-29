# Solapamiento de backups y tamaño de copias Gmail en Drive

## 1) Evitar dos ejecuciones a la vez (misma tarea + misma cuenta)

A partir de la lógica en `app.services.backup_concurrency_service`:

- Antes de encolar Celery (ejecución manual **Ejecutar** y disparo programado diario), se comprueba si ya existe un `BackupLog` en estado `pending`, `queued` o `running` para la **misma tarea**, **misma cuenta** y el **mismo tipo**: Gmail o Drive.
- **Drive** y **Gmail** se tratan por separado (una tarea `full` puede tener un Drive activo y aun así intentar Gmail si Gmail está libre).
- Si **todo** lo que habría que encolar está bloqueado, la API responde **409** con detalle `all_runs_active`.
- Si solo parte de las cuentas estaban ocupadas, se encola el resto y en la respuesta aparece `skipped_due_to_active`.

Los workers también comprueban al arrancar: si otro job dejó ya un log activo con otro `celery_task_id`, el segundo worker **no crea** un segundo log y termina devolviendo el existente (mensaje de progreso `worker_skipped`).

> Límite: la deduplicación es por **definición de tarea** (`backup_tasks.id`), no entre dos tareas distintas que apunten a la misma cuenta. Si necesitás un candado global por cuenta, habría que extender la regla.

## 2) ¿Por qué “crece” el backup de Gmail en Drive día a día?

Comportamiento **esperado** del diseño actual:

1. **GYB** descarga correo de forma **incremental** sobre la carpeta de trabajo local (`/var/msa/work/gmail/<email>/`): no re-baja todo el historial en cada ejecución salvo que se pierda el estado local o se borre esa carpeta.
2. El push al vault usa **`rclone copy`** hacia una ruta fija: `1-GMAIL/gyb_mbox` bajo el Shared Drive del usuario (`vault_layout`). Eso **actualiza y añade** ficheros; no crea por defecto una carpeta nueva por día **para Gmail**.
3. **El tamaño sube** si llegan **mensajes nuevos**, adjuntos, o si el buzón en Google tiene más datos que antes. No implica por sí solo una “duplicación completa diaria”.

Confusiones frecuentes:

- **Drive “MI UNIDAD”** sí puede usar `filters_json.drive_layout: "dated_run"`, que genera carpetas con fecha bajo `2-DRIVE/MSA_Runs/...`. Eso **sí** acumula snapshots **por ejecución**. No es lo mismo que `1-GMAIL/gyb_mbox`.
- La opción **`gmail_purge_gyb_workdir_after_vault_verified`**: si está activa, tras verificar con `rclone check` se **vacía** el workdir de GYB. En la siguiente corrida GYB puede tener que **reconstruir** mucho contenido local y el `copy` al vault puede transferir de nuevo grandes volúmenes. Úsala solo si entendés el impacto.
- Comparar “la copia de ayer” vs “la de otro día”: en Drive, revisá si estás mirando **toda** la unidad compartida, **solo** `1-GMAIL`, o carpetas `MSA_Runs` de Drive.

## 3) Recomendaciones

- Para Gmail incremental “estable”, mantené **un solo destino** `1-GMAIL/gyb_mbox` y evitá purgar el workdir salvo necesidad y política clara.
- Para Drive, si no querés crecimiento por snapshots, usá layout continuo (`2-DRIVE/_sync`) en lugar de `dated_run`, o ajustá retención (`drive_retention` / políticas de la tarea).
- Si un backup quedó colgado en `running`, corregilo (cancelar lote / marcar log) antes de forzar de nuevo; si no, la nueva regla seguirá viendo “activo” y bloqueará encolados.
