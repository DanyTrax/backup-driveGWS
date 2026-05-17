import { Alert, Spinner } from 'flowbite-react'
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

export function VaultSharedDriveItemCountSessionPanel({
  session,
  showHeading = true,
}: {
  session: VaultSharedDriveItemCountSession
  showHeading?: boolean
}) {
  const running = session.state === 'running'
  const now = useNowTick(running)

  if (session.state === 'idle') return null

  const started = session.started_at ? Date.parse(session.started_at) : NaN
  const elapsedMs =
    running && session.started_at && !Number.isNaN(started) ? Math.max(0, now - started) : null

  return (
    <div className="text-sm space-y-2">
      {showHeading ? (
        <div className="font-medium text-slate-800 dark:text-slate-100">
          Conteo de ítems — Shared Drive de respaldo (Mantenimiento)
        </div>
      ) : null}

      {running ? (
        <div className="flex flex-wrap items-start gap-3">
          <Spinner size="md" className="shrink-0" />
          <div className="min-w-0 flex-1 space-y-1">
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
                La primera cifra aparece al terminar la primera página de la API (puede tardar unos segundos).
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

      {session.state === 'success' && session.result ? (
        <div className="space-y-1 text-slate-700 dark:text-slate-200">
          {session.result.shared_drive_name || session.result.shared_drive_id ? (
            <p>
              Unidad:{' '}
              <span className="font-medium">
                {session.result.shared_drive_name ?? session.result.shared_drive_id}
              </span>
            </p>
          ) : null}
          {session.result.ok ? (
            <>
              <p>
                <span className="font-semibold tabular-nums">
                  {session.result.total_items.toLocaleString('es-AR')}
                </span>{' '}
                ítems ({session.result.file_count.toLocaleString('es-AR')} archivos,{' '}
                {session.result.folder_count.toLocaleString('es-AR')} carpetas).
                {session.finished_at ? (
                  <>
                    {' '}
                    Fin:{' '}
                    <span className="text-slate-500">{formatLogDateTime(session.finished_at)}</span>
                  </>
                ) : null}
              </p>
              {session.result.remaining_until_limit != null ? (
                <p className="text-slate-500 text-xs">
                  Margen hasta ~{session.result.item_limit.toLocaleString('es-AR')} ítems:{' '}
                  <span className="font-medium text-slate-700 dark:text-slate-200 tabular-nums">
                    {session.result.remaining_until_limit.toLocaleString('es-AR')}
                  </span>
                </p>
              ) : null}
            </>
          ) : (
            <p className="text-amber-700 dark:text-amber-300">
              {session.result.error ?? 'Conteo no OK (revisá configuración vault).'}
            </p>
          )}
        </div>
      ) : null}

      {session.state === 'success' && !session.result ? (
        <Alert color="warning">
          {session.result_parse_error
            ? 'El resultado guardado en el servidor no tiene el formato esperado. Volvé a ejecutar el conteo desde Mantenimiento.'
            : 'Conteo marcado como finalizado pero no hay totales guardados. Revisá el worker o reejecutá el conteo.'}
        </Alert>
      ) : null}

      {session.state === 'failure' ? (
        <p className="text-red-700 dark:text-red-300">
          {session.error ?? 'Falló el job de conteo en el worker.'}
        </p>
      ) : null}
    </div>
  )
}
