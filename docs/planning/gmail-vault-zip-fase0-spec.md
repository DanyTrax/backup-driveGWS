# Plan Gmail vault (ZIP) + visor — Especificación y fases

Documento **vivo**: decisiones de producto (Fase 0) + **checklist de ejecución** técnica (Fases 1–8).

---

## 0. Resumen acordado (conversación)

- **Tarea Gmail:** GYB en servidor con una cadencia; **subida al vault** en ZIP con otra (día de semana anclaje, semana o mes). Parámetros en `filters_json` / formulario.
- **Bootstrap:** Si en vault/BD **no** hay sellado previo → **completo** GYB; opción de subida inmediata del primer ZIP o esperar al día anclaje (`bootstrap_upload_immediate`).
- **Tras borrar workdir local:** Reconstruir desde Gmail solo el tramo **después del último sellado en vault** (watermark/fecha + `overlap_days` configurable, default recomendado `1`).
- **Visor “GYB en Drive”:** **Por cuenta**; alcance: **día**, **rango inicio–fin**, **mes** (atajo), **todo** lo disponible compatible; progreso, TTL en servidor, **unificar** zips → misma UX que bandeja de trabajo GYB.
- **Legacy:** Convivencia con `1-GMAIL/gyb_mbox` (eml) hasta migración; modo `gmail_vault_packaging`: `legacy_eml` | `zip_only` | `mixed`.

---

## 0.1 Modos de restauración / materialización (visor vault)

| Modo API/UI | Descripción |
|-------------|-------------|
| `single_day` | Un `YYYY-MM-DD`; bajar ZIP(s) que cubran ese día. |
| `date_range` | `date_from` … `date_to` explícitos. |
| `month` | Atajo: mes calendario (equivale a rango prellenado). |
| `all` | Todo lo indexado en vault para la cuenta (límites de cuota/TTL). |

Siempre parametrizado por **`account_id`** y opcionalmente **`task_id`** si el layout en Drive depende de la definición de tarea.

---

## 0.2 Checklist de fases de implementación

| Fase | Contenido | Estado |
|------|-----------|--------|
| **1** | Modelo BD: estado vault por `(cuenta, tarea)` + sesiones de materialización; migración Alembic. | ✅ hecho (`0015_*`, `gmail_vault.py`) |
| **2** | Esquema JSON manifiesto ZIP + rutas bajo `1-GMAIL/zips/…` (doc + validador). | ✅ hecho (`gmail_vault_manifest`, `gmail_vault_zip_layout`, tests) |
| **3** | Motor backup: ZIP al vault, planificación semanal/mensual, integración `run_gmail_backup`. | ✅ hecho (v1: GYB workdir → zip + manifiesto + rclone; estado en BD) |
| **4** | Schemas/API tareas: validación `filters_json` vault ZIP + formulario UI (Gmail/Full). | ✅ |
| **5** | APIs `materialize` + progreso + purge TTL. | ✅ |
| **6** | Frontend: pestaña vault materialización / visor. | ✅ |
| **7** | Migración legacy → zip (opcional, documentada). | ☐ |
| **8** | Tests integración, límites disco, métricas. | ☐ |

---

## 1. Alcance y objetivos

| Ítem | Descripción | Estado |
|------|-------------|--------|
| G1 | Menos ítems en Shared Drive vía ZIPs por periodo (vs muchos `.eml`). | ☐ |
| G2 | Descarga GYB completa o parcial según **estado vault + BD** (sin full innecesario). | ☐ |
| G3 | Cadencia **GYB en servidor** ≠ cadencia **subida ZIP** (día de semana / semana / mes). | ☐ |
| G4 | Manifiesto + logs auditables. | ☐ |
| G5 | Visor vault: rango/fechas, progreso, TTL, unificar zips → experiencia tipo bandeja GYB. | ☐ |
| G6 | Convivencia o migración desde `1-GMAIL/gyb_mbox` (legacy). | ☐ |

---

## 2. Sellado y watermark (crítico)

| Opción | Descripción | ¿Elegida? |
|--------|-------------|-----------|
| A | Solo **fecha fin** (`last_sealed_date`) en TZ definida. | ☐ |
| B | **Fecha fin** + **solapamiento** configurable (0–N días). | ☑ **B** (impl. default `overlap_days=1` en tarea) |
| C | **Watermark fino Gmail**: `historyId` / estado GYB en manifiesto + BD (`watermark_json`). | ☑ **C** (campo `watermark_json`) |
| D | Lista exhaustiva Message-Ids en manifiesto | ☐ opcional futuro |

**Timezone “día D”:** alineado a `backup_tasks.timezone` (default `America/Bogota`).

**Decisión final (texto):**

```
B + C: last_sealed_at en BD + watermark_json evolutivo; overlap_days en filters_json (default 1).
```

---

## 3. Semántica “semana” y “mes”

### 3.1 Semana

| Opción | Definición | ¿Elegida? |
|--------|------------|-----------|
| S1 | Calendario en TZ de tarea (definir lun–dom vs dom–sáb en implementación). | ☑ **S1** (detalle en Fase 3) |
| S2 | Rodante desde `last_sealed`. | ☐ |

### 3.2 Mes

| Opción | Definición | ¿Elegida? |
|--------|------------|-----------|
| M1 | Mes calendario. | ☑ **M1** preferido; M2 si se expone flag |
| M2 | Desde último sellado hasta anclaje. | ☐ |

### 3.3 Varias subidas por mes — TBD en Fase 3 si hace falta `vault_zip_slices_per_month`.

---

## 4. Día de anclaje para subida al vault

| Campo | Valor / regla |
|-------|----------------|
| Día de semana | `vault_anchor_dow` 0–6 en `filters_json` (convención Python `weekday()` documentada) |
| Mensual | `vault_anchor_dom` opcional 1–28 |
| Mismo run | GYB + zip + upload en una corrida si “toca” día de subida; si no, solo GYB cuando aplique schedule |

---

## 5. Primera copia (bootstrap)

| Pregunta | Respuesta |
|----------|-----------|
| Sin ZIP/registro en vault | Full GYB |
| Tras primer full | `bootstrap_upload_immediate` en `filters_json` |

---

## 6. Tras borrado del workdir en servidor

| Comportamiento | Confirmado |
|----------------|------------|
| Tramo desde vault sellado − overlap | Sí |
| No re-full sin re-semilla | Sí |
| Primer ZIP post-wipe cubre hueco hasta cierre de periodo | Sí |

---

## 7. Layout en Google Drive (bajo `1-GMAIL/`)

```text
1-GMAIL/
  zips/
    {account_id}/                 # UUID estable (recomendado)
      …                           # WEEKLY/MONTHLY + manifiestos (Fase 2–3)
  gyb_mbox/                       # LEGACY
```

Identificador de carpeta por cuenta: **`account_id`** (UUID) en árbol zip; email en manifiesto legible.

---

## 8. Formato ZIP y manifiesto

Versión inicial **`manifest_version: 1`** implementada en `app/schemas/gmail_vault_manifest.py`:

- `account_id`, `account_email`, `task_id`, `timezone`, `period_start` / `period_end`, `overlap_days_applied`, `seal_kind`, `gmail_watermark`, `backup_log_id`, `created_at`, `gyb_version_note`, `zip_basename`, `files[]` con `rel_path`, `size_bytes`, `sha256` opcional.

Rutas relativas al vault (`dest:` carpeta cuenta): `app/services/gmail_vault_zip_layout.py` — `1-GMAIL/zips/{account_id}/{BOOTSTRAP|WEEKLY|MONTHLY|MANUAL}/YYYY-MM-DD__YYYY-MM-DD.zip` + `.manifest.json`.

Compresión del `.zip`: pendiente Fase 3 (default previsto `deflate`).

---

## 9. Retención y materialización (visor vault)

| Parámetro | Default | Notas |
|-----------|---------|--------|
| TTL | 15 días | configurable por solicitud con tope máx (Fase 5) |
| Reset TTL al ampliar | Sí | misma sesión documentada en Fase 5 |

---

## 10. Unificación “como bandeja GYB”

Directorio base: `/var/msa/work/gmail-vault-pull/{account_id}/{session_id}/` (email opcional en log). Estructura compatible con visor GYB existente (Fase 5–6).

---

## 11. Tarea Gmail — `filters_json` (claves previstas)

| Clave | Tipo | Descripción |
|-------|------|-------------|
| `gmail_vault_packaging` | string | `legacy_eml` \| `zip_only` \| `mixed` |
| `vault_zip_cadence` | string | `weekly` \| `monthly` \| `none` (solo bootstrap, sin recurrencia) |
| `vault_anchor_dow` | int | 0–6 |
| `vault_anchor_dom` | int? | 1–28 |
| `bootstrap_upload_immediate` | bool | |
| `overlap_days` | int | default `1` |
| `retention_local_gyb_days` | int? | opcional |

---

## 12. API — superficie

| Método | Ruta | Estado |
|--------|------|--------|
| GET | `/tasks/{id}/backup-wave-status` | ✅ |
| POST | `/vault/gmail/materialize` | ✅ |
| GET | `/vault/gmail/materialize/{session_id}` | ✅ |
| DELETE | `/vault/gmail/materialize/{session_id}` | ✅ |

---

## 13. Criterios de salida Fase 0

- [x] Plan maestro y modos visor reflejados en §0–0.1.
- [ ] Congelación fecha: al cerrar Fase 3 núcleo.
- [ ] Tablas 3.3 / 4 finos tras primera implementación.

---

## 14. Historial de cambios

| Fecha | Cambio |
|-------|--------|
| — | Creación plantilla |
| 2026-05-08 | Añadido plan maestro, modos visor, decisiones por defecto B+C+S1+M1 |
| 2026-05-08 | **Fase 4:** validación `filters_json` vault ZIP en tareas + UI Gmail/Full. |
| 2026-05-08 | **Fase 5:** APIs `/api/vault/gmail/materialize*`; Celery materialize; TTL + limpieza en `cleanup_expired_sessions`. |
| 2026-05-08 | **Fase 6:** UI «ZIP vault Gmail» (`/vault-gmail-zip`), hooks API materialize, accesos desde Bóveda Drive. |
