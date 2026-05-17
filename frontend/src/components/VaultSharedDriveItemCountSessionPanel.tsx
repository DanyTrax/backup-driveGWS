import { Alert } from 'flowbite-react'
import { useEffect, useState } from 'react'
import type { VaultSharedDriveItemCountSession } from '../api/types'
import { formatLogDateTime } from '../utils/logDateFormat'

function formatDurationMs(ms: number): string {
  const s = Math.floor(ms / 1000)
  const m = Math.floor(s / 60)
  const r = s % 60
  if (m >= 60) {
    const h = Math.floor(m / 60)
    const mm = m % 60
    return `${h}h ${mm}m ${r}s`
  }
  if (m > 0) return `${m}m ${r}s`
  return `${r}s`
}

function useNowTick(active: boolean) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return
    const t = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(t)
  }, [active])
  return now
}

function normalizeSessionState(
  s: string | undefined | null,
  taskId: string | undefined | null,
): string {
  if (s == null || String(s).trim() === '') return 'unknown'
  const x = String(s).trim().toLowerCase()
  // Misma semántica que el API: encolado → "en curso" solo si hay task_id
  if (x === 'pending' || x === 'queued' || x === 'received' || x === 'retry') {
    if (taskId == null || String(taskId).trim() === '') return 'failure'
    return 'running'
  }
  return x
}

function PartialCountProgress({
  session,
  emphasize,
}: {
  session: VaultSharedDriveItemCountSession
  emphasize?: boolean
}) {
  const items = session.progress_items
  const pages = session.pages_fetched
  if (
    (items == null || items <= 0) &&
    (pages == null || pages <= 0)
  ) {
    return null
  }
  return (
    <div
      className={
        emphasize
          ? 'rounded-md border border-amber-200 dark:border-amber-800 bg-amber-50/80 dark:bg-amber-950/30 px-3 py-2 space-y-1'
          : 'space-y-1'
      }
    >
      <p className="font-medium text-slate-800 dark:text-slate-100">
        Avance parcial (aprox., según páginas ya recorridas en la API de Drive):
      </p>
      {items != null && items > 0 ? (
        <p className="text-slate-700 dark:text-slate-200">
          <span className="font-semibold tabular-nums">{items.toLocaleString('es-AR')}</span> ítems contados hasta la
          última página publicada
          {pages != null && pages > 0 ? (
            <>
              {' '}
              (<span className="tabular-nums">{pages.toLocaleString('es-AR')}</span>{' '}
              {pages === 1 ? 'página' : 'páginas'}; hasta ~1000 ítems por página).
            </>
          ) : null}
        </p>
      ) : pages != null && pages > 0 ? (
        <p className="text-slate-700 dark:text-slate-200">
          <span className="font-semibold tabular-nums">{pages.toLocaleString('es-AR')}</span>{' '}
          {pages === 1 ? 'página' : 'páginas'} de resultados de la API procesadas.
        </p>
      ) : null}
      {session.progress_updated_at ? (
        <p className="text-xs text-slate-500">
          Última actualización del worker: {formatLogDateTime(session.progress_updated_at)}
        </p>
      ) : null}
      {session.task_id ? (
        <p className="text-xs text-slate-500">
          Celery id: <code className="break-all">{session.task_id}</code>
        </p>
      ) : null}
    </div>
  )
}

function CssSpinner({ className = '' }: { className?: string }) {
  return (
    <div
      className={`h-8 w-8 shrink-0 rounded-full border-2 border-blue-600 border-t-transparent dark:border-blue-400 animate-spin ${className}`}
      role="status"
      aria-label="Cargando"
    />
  )
}

export function VaultSharedDriveItemCountSessionPanel({
  session,
  showHeading = true,
}: {
  session: VaultSharedDriveItemCountSession
  showHeading?: boolean
}) {
  const stRaw = normalizeSessionState(session.state, session.task_id)
  const st =
    stRaw === 'running' && (session.task_id == null || String(session.task_id).trim() === '')
      ? 'failure'
      : stRaw
  const hasPartialProgress =
    (session.progress_items != null && session.progress_items > 0) ||
    (session.pages_fetched != null && session.pages_fetched > 0)

  const progressUpdatedMs = session.progress_updated_at ? Date.parse(session.progress_updated_at) : NaN
  const progressFresh =
    !Number.isNaN(progressUpdatedMs) && Date.now() - progressUpdatedMs < 45 * 60 * 1000

  /** El API a veces devuelve failure por heurísticas Celery/Redis aunque el worker sigue publicando páginas. */
  const runFailureButLikelyStillCounting = st === 'failure' && hasPartialProgress && progressFresh

  const showRunningChrome = running || runFailureButLikelyStillCounting
  const now = useNowTick(showRunningChrome)

  if (st === 'idle') return null

  const started = session.started_at ? Date.parse(session.started_at) : NaN
  const elapsedMs =
    showRunningChrome && session.started_at && !Number.isNaN(started)
      ? Math.max(0, now - started)
      : null

  const res = session.result
  const totalItems = res != null && typeof res.total_items === 'number' ? res.total_items : 0
  const fileCount = res != null && typeof res.file_count === 'number' ? res.file_count : 0
  const folderCount = res != null && typeof res.folder_count === 'number' ? res.folder_count : 0
  const itemLimit = res != null && typeof res.item_limit === 'number' ? res.item_limit : 400_000

  return (
    <div className="text-sm space-y-2">
      {showHeading ? (
        <div className="font-medium text-slate-800 dark:text-slate-100">
          Conteo de ítems — Shared Drive de respaldo (Mantenimiento)
        </div>
      ) : null}

      {showRunningChrome ? (
        <div className="flex flex-wrap items-start gap-3">
          <CssSpinner />
          <div className="min-w-0 flex-1 space-y-1">
            {runFailureButLikelyStillCounting ? (
              <Alert color="warning">
                El servidor marcó «fallo» en la sesión pero el último avance en Redis es reciente: es posible que el
                conteo siga en el worker. Los números de abajo son aproximados (páginas ya procesadas). Si dejan de
                subir, revisá logs del worker.
              </Alert>
            ) : null}
            <p className="font-medium text-slate-800 dark:text-slate-100">
              Recorriendo la unidad con la API de Google…
            </p>
            <p className="text-slate-600 dark:text-slate-300">
              Inicio local:{' '}
              <span className="font-medium">{formatLogDateTime(session.started_at)}</span>
              {elapsedMs != null ? (
                <>
                  {' '}
                  · Tiempo transcurrido:{' '}
                  <span className="font-medium tabular-nums">{formatDurationMs(elapsedMs)}</span>
                </>
              ) : null}
            </p>
            {session.progress_items != null && session.progress_items > 0 ? (
              <p className="text-slate-700 dark:text-slate-200">
                <span className="font-semibold tabular-nums">
                  {session.progress_items.toLocaleString('es-AR')}
                </span>{' '}
                ítems contados hasta ahora
                {session.pages_fetched != null && session.pages_fetched > 0 ? (
                  <>
                    {' '}
                    (<span className="tabular-nums">{session.pages_fetched.toLocaleString('es-AR')}</span>{' '}
                    {session.pages_fetched === 1 ? 'página' : 'páginas'} de resultados de la API; hasta ~1000 ítems por
                    página).
                  </>
                ) : null}
              </p>
            ) : (
              <p className="text-slate-500 text-xs">
                La primera cifra aparece al terminar la primera página de la API (puede tardar unos segundos). Si el
                worker Celery no está en marcha, el conteo no avanza: revisá el contenedor{' '}
                <code className="text-[10px]">worker</code> y Redis.
              </p>
            )}
            {session.progress_updated_at ? (
              <p className="text-xs text-slate-500">
                Última actualización: {formatLogDateTime(session.progress_updated_at)}
              </p>
            ) : null}
            <p className="text-xs text-slate-500">
              Celery id: <code className="break-all">{session.task_id ?? '—'}</code>
            </p>
          </div>
        </div>
      ) : null}

      {st === 'success' && res ? (
        <div className="space-y-1 text-slate-700 dark:text-slate-200">
          {res.shared_drive_name || res.shared_drive_id ? (
            <p>
              Unidad:{' '}
              <span className="font-medium">{res.shared_drive_name ?? res.shared_drive_id}</span>
            </p>
          ) : null}
          {res.ok ? (
            <>
              <p>
                <span className="font-semibold tabular-nums">{totalItems.toLocaleString('es-AR')}</span> ítems (
                {fileCount.toLocaleString('es-AR')} archivos, {folderCount.toLocaleString('es-AR')} carpetas).
                {session.finished_at ? (
                  <>
                    {' '}
                    Fin:{' '}
                    <span className="text-slate-500">{formatLogDateTime(session.finished_at)}</span>
                  </>
                ) : null}
              </p>
              {res.remaining_until_limit != null ? (
                <p className="text-slate-500 text-xs">
                  Margen hasta ~{itemLimit.toLocaleString('es-AR')} ítems:{' '}
                  <span className="font-medium text-slate-700 dark:text-slate-200 tabular-nums">
                    {res.remaining_until_limit.toLocaleString('es-AR')}
                  </span>
                </p>
              ) : null}
              {totalItems >= itemLimit ? (
                <Alert color="warning">
                  El conteo alcanza o supera el límite de referencia de Google (~400k ítems). Conviene planificar otra
                  unidad o depuración antes de seguir cargando respaldos.
                </Alert>
              ) : null}
            </>
          ) : (
            <p className="text-amber-700 dark:text-amber-300">
              {res.error ?? 'Conteo no OK (revisá configuración vault).'}
            </p>
          )}
        </div>
      ) : null}

      {st === 'success' && !res ? (
        <Alert color="warning">
          {session.result_parse_error
            ? 'El resultado guardado en el servidor no tiene el formato esperado. Volvé a ejecutar el conteo desde Mantenimiento (revisá logs del worker).'
            : 'Conteo marcado como finalizado pero no hay totales guardados. ¿El worker terminó sin publicar resultado? Revisá logs de Celery y reejecutá el conteo.'}
        </Alert>
      ) : null}

      {st === 'failure' && !runFailureButLikelyStillCounting ? (
        <div className="space-y-3">
          <PartialCountProgress session={session} emphasize />
          <p className="text-red-700 dark:text-red-300">
            {session.error ??
              (stRaw === 'running'
                ? 'Sesión «en curso» sin id de tarea en el servidor (Redis incompleto). Reejecutá el conteo o limpiá la clave en Redis.'
                : 'Falló el job de conteo en el worker.')}
          </p>
          {!hasPartialProgress ? (
            <p className="text-slate-500 text-xs">
              No hay cifras parciales guardadas todavía. Cuando el worker publique la primera página en Redis, acá
              verás un aproximado aunque falle el resto del flujo.
            </p>
          ) : null}
        </div>
      ) : null}

      {st !== 'running' && st !== 'success' && st !== 'failure' ? (
        <Alert color="warning">
          Estado de sesión no reconocido: <code className="text-xs">{String(session.state)}</code>. Datos: task_id{' '}
          {session.task_id ?? '—'}.
        </Alert>
      ) : null}
    </div>
  )
}
