# Plan: layout de vault `1-GMAIL` / `2-DRIVE` y evolución

Este documento fija lo **implementado** en código y lo **pendiente** respecto al diseño acordado (Drive como verdad, VPS como trabajo, retención por tarea).

## Implementado (backend)

| Área | Comportamiento |
|------|----------------|
| `app/services/vault_layout.py` | Constantes `1-GMAIL`, `2-DRIVE`, subpath `1-GMAIL/gyb_mbox`, destino continuo `2-DRIVE/_sync`, `drive_dest_subpath_for_task()` con `drive_run_kind` → `(TOTAL)` / `(SNAPSHOT)`. |
| Backup Gmail | Tras GYB + import Maildir + manifest: `rclone copy` del **workdir GYB** a `dest:1-GMAIL/gyb_mbox/`. Subida requiere `drive_vault_folder_id` salvo `vault_gmail_disable_push`. Opcional `gmail_purge_gyb_workdir_after_vault_verified: true`: `rclone check --one-way` y si OK vacía el workdir GYB en el VPS; si el check **falla**, el **job falla** y no se borra nada. Por defecto la purga está **apagada**. |
| Backup Drive (archivos) | Destino rclone bajo **`2-DRIVE/...`** por defecto (`vault_separated_layout` por defecto `true`). Modo `dated_run`: `2-DRIVE/MSA_Runs/<stamp>` o `… (TOTAL|SNAPSHOT)` si `filters_json.drive_run_kind`. Sin `dated_run`: `2-DRIVE/_sync`. |
| Retención `MSA_Runs` | `drive_retention.prune_after_drive_backup` busca `MSA_Runs` bajo **`2-DRIVE`** cuando el layout separado está activo. |
| Legado | `filters_json.vault_legacy_layout: true` restaura paths de Drive en la raíz del vault (sin `2-DRIVE`), y Gmail al vault solo con `vault_gmail_push: true`. |

## Filtros JSON relevantes

- `vault_separated_layout` / `vault_legacy_layout` — layout v2 vs legado.
- `vault_gmail_disable_push` — no subir GYB a `1-GMAIL/` (solo local/Maildir).
- `drive_layout: dated_run`, `dated_run_prefix`, `drive_run_kind` (`TOTAL` | `SNAPSHOT`).
- `drive_dest_use_continuous_dir: false` — sincronizar en `2-DRIVE/` raíz en lugar de `2-DRIVE/_sync`.
- `gmail_purge_gyb_workdir_after_vault_verified: true` — vacía `/var/msa/work/gmail/<email>/` solo si `rclone check` al vault OK (requiere subida a `1-GMAIL` activa).

## Pendiente (producto / roadmap)

1. **UI de tareas** — campos para `drive_run_kind`, topes `keep_drive_totals` / `keep_snapshot_*` (hoy solo `keep_drive_snapshots` en retención de carpetas bajo `MSA_Runs`).
2. **SNAPSHOT delta** — `rclone --compare-dest` contra el último `(TOTAL)`; política explícita en tarea.
3. **Visor + caché 48 h** — API/SPA y TTL local (no cubierto aquí).
4. **Poda separada** — máximo N `(TOTAL)` y ventana de días para `(SNAPSHOT)` como en la especificación de negocio (ampliar `retention_policy_json` + jobs).
5. **Docs de usuario** — guía C/D: actualizar árbol de ejemplo a `1-GMAIL/gyb_mbox` y `2-DRIVE/…`.

## Despliegue

Tras actualizar: las **tareas existentes** sin `vault_legacy_layout` pasan a escribir bajo `2-DRIVE/_sync` o `2-DRIVE/MSA_Runs/...`. Datos antiguos en la raíz del vault siguen ahí; migración manual o tarea one-shot si hace falta.
