# Especificación Fase 0 — Gmail → servidor → ZIP → vault + visor

Documento vivo para **congelar decisiones** antes de implementar. Completar cada tabla; marcar **DECIDIDO** y fecha cuando se cierre el ítem.

**Referencia del plan de ejecución:** conversación acordada (fases 1–8). Este archivo es el **anexo operativo** de la Fase 0.

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

**Pregunta:** ¿Cómo sabemos con exactitud “hasta dónde llega lo ya resguardado en vault”?

| Opción | Descripción | ¿Elegida? |
|--------|-------------|-----------|
| A | Solo **fecha fin** (`last_sealed_date`) en TZ definida. | ☐ |
| B | **Fecha fin** + **solapamiento** configurable (0–N días). | ☐ |
| C | **Watermark fino Gmail**: `historyId` / estado interno GYB guardado en manifiesto + BD. | ☐ |
| D | Lista de **Message-Ids** o UIDs incluidos en cada ZIP (manifiesto pesado pero preciso). | ☐ |

**Decisión final (texto):**

```
(ej.: Combinamos C + B con overlap_days=1 por defecto, sobreescribible en la tarea)
```

**Timezone “día D” para nombres de periodo y sellado:**

| Valor | Notas |
|-------|--------|
| TZ fija tarea: `________________` | Debe alinearse con carpetas por fecha de GYB si aplica. |

---

## 3. Semántica “semana” y “mes”

### 3.1 Semana

| Opción | Definición | ¿Elegida? |
|--------|------------|-----------|
| S1 | Calendario **lun–dom** (o dom–sáb) en TZ de la tarea. | ☐ |
| S2 | **Rodante**: desde `last_sealed` hasta `last_sealed + 7 días`. | ☐ |
| S3 | Otra: `________________________________` | ☐ |

### 3.2 Mes

| Opción | Definición | ¿Elegida? |
|--------|------------|-----------|
| M1 | **Mes calendario** (día 1 → último día del mes). | ☐ |
| M2 | Desde **último sellado** hasta el **día de anclaje** que cae en el mes. | ☐ |
| M3 | Otra: `________________________________` | ☐ |

### 3.3 Varias subidas por mes (opcional)

| Parámetro | Valor |
|-----------|--------|
| ¿Cuántos ZIPs máx. por mes? | p. ej. 1 / 4 / N: ____ |
| Si N>1, franjas fijas | p. ej. 1–7, 8–14, … o `________________` |

---

## 4. Día de anclaje para subida al vault

| Campo | Valor / regla |
|-------|----------------|
| Día de semana de **cierre + subida** (0=dom … 6=sáb o convención acordada) | ____ |
| Si cadencia es **mensual**, ¿subida solo si el anclaje cae en día D o cualquier ejecución del día 1? | ____ |
| ¿El mismo run hace **GYB** + **ZIP** + **upload** o jobs separados? | ____ |

---

## 5. Primera copia (bootstrap)

| Pregunta | Respuesta |
|----------|-----------|
| Si **no hay** ZIP/manifiesto en vault ni registro en BD para la cuenta, ¿full GYB siempre? | Sí / No / Condición: ____ |
| Tras primer full en disco, ¿subida **inmediata** o **esperar** al primer día de anclaje? | Inmediata / Esperar / Flag tarea: ____ |
| Nombre del primer ZIP / carpeta FULL | `________________` |

---

## 6. Tras borrado del workdir en servidor

| Comportamiento | Confirmado (Sí/No) |
|----------------|---------------------|
| Consultar vault/BD → descendente solo desde `last_sealed − overlap`. | ☐ |
| No re-full del buzón salvo “re-semilla” explícita. | ☐ |
| Primer ZIP tras rehidratación incluye el **tramo faltante** hasta el cierre del periodo actual. | ☐ |

---

## 7. Layout en Google Drive (bajo `1-GMAIL/`)

**Propuesta base (editar si se decide otra):**

```text
1-GMAIL/
  zips/
    {identificador_cuenta}/     # email normalizado o account_id
      manifest-index.json       # opcional: índice de periodos
      WEEKLY/ o MONTHLY/ o BOTH/
        YYYY-MM-DD__YYYY-MM-DD.zip
        YYYY-MM-DD__YYYY-MM-DD.manifest.json
  gyb_mbox/                     # LEGACY: eml sueltos (convivencia o solo lectura)
```

| Decisión | Valor |
|----------|--------|
| Identificador de carpeta por cuenta | email / uuid / otro: ____ |
| ¿Se elimina o congela escritura en `gyb_mbox` para cuentas en modo ZIP? | ____ |

---

## 8. Formato ZIP y manifiesto

| Campo manifiesto | Incluir (Sí/No) |
|------------------|-----------------|
| `manifest_version` | ☐ |
| `account_id` / `email` | ☐ |
| `task_id` | ☐ |
| `period_start`, `period_end` (ISO + TZ) | ☐ |
| `overlap_days_applied` | ☐ |
| `gmail_watermark` (objeto libre) | ☐ |
| Lista de archivos rel_path + size + sha256 | ☐ |
| `gyb_version` / build | ☐ |

| Compresión | `deflate` / `store` / otra: ____ |
|------------|-------------------------------------|
| Límite tamaño ZIP antes de dividir | ____ GB o N ficheros |

---

## 9. Retención y materialización (visor vault)

| Parámetro | Default | Máximo permitido |
|-----------|---------|------------------|
| TTL materialización servidor | 15 días | ____ |
| Override por solicitud en UI | Sí / No | máx ____ |
| Cuota GB por cuenta en temp | ____ | ____ |
| ¿Reset de TTL al ampliar rango en la misma sesión? | Sí / No | Regla: ____ |

---

## 10. Unificación “como bandeja GYB”

| Pregunta | Respuesta |
|----------|-----------|
| Directorio destino unificado | p. ej. `/var/msa/work/gmail-vault-pull/{email}/{session}/` |
| ¿Misma estructura que GYB actual para abrir msg-db / visor? | Sí / No: ____ |
| ¿Límite de zips a fusionar en una sola sesión? | N = ____ |

---

## 11. Tarea Gmail — parámetros nuevos (`filters_json` / columnas)

Listar claves exactas para implementación (rellenar):

| Clave JSON | Tipo | Descripción |
|------------|------|-------------|
| `gmail_vault_packaging` | enum | `legacy_eml \| zip_only \| mixed` |
| `vault_zip_cadence` | enum | `weekly \| monthly \| …` |
| `vault_anchor_dow` | int | día semana anclaje |
| `vault_anchor_dom` | int? | día del mes si aplica |
| `bootstrap_upload_immediate` | bool | |
| `overlap_days` | int | default 0 o 1 |
| `retention_local_gyb_days` | int? | purge opcional post-upload |
| `…` | | |

---

## 12. API — borrador de superficie

| Método | Ruta | Propósito |
|--------|------|-----------|
| GET | `/tasks/{id}/backup-wave-status` | ✅ existente |
| POST | `/vault/gmail/materialize` | Nueva sesión descarga+unión |
| GET | `/vault/gmail/materialize/{session_id}` | Estado / progreso |
| DELETE | `/vault/gmail/materialize/{session_id}` | Cancelar / purga manual |

*(Ajustar prefijos al router real del proyecto.)*

---

## 13. Criterios de salida Fase 0

- [ ] Todas las tablas **2, 3, 4, 5, 7, 8** tienen al menos una opción **DECIDIDO**.
- [ ] Redactado un párrafo “**Comportamiento tras borrado local**” firmado por producto/ops.
- [ ] Decisión explícita **legacy vs zip-only** para cuentas nuevas.
- [ ] Fecha de congelación: `____-____-____`

---

## 14. Historial de cambios

| Fecha | Autor | Cambio |
|-------|-------|--------|
| | | Creación plantilla |
