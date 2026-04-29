import { Badge, Button, Card, Modal, Select } from 'flowbite-react'
import { useState } from 'react'
import type { AxiosError } from 'axios'
import toast from 'react-hot-toast'
import { HiDownload, HiTrash, HiX } from 'react-icons/hi'
import {
  useBackupLogDetail,
  useBackupLogs,
  useCancelBackupBatch,
  useCancelBackupLog,
  useDeleteBackupLog,
  useDeleteBackupLogsBulk,
  useProfile,
  useRetryGmailVault,
  downloadBackupLogsPdf,
} from '../api/hooks'
import type { BackupLog } from '../api/types'

function truncateDetail(s: string | null | undefined, max = 140): string {
  if (!s?.trim()) return '—'
  const t = s.trim()
  return t.length <= max ? t : `${t.slice(0, max)}…`
}

function humanBytes(n: number) {
  if (!n) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0
  let v = n
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i++
  }
  return `${v.toFixed(1)} ${units[i]}`
}

/** Texto legible del último evento Redis (backup en curso). */
function describeLiveProgress(p: Record<string, unknown> | null | undefined): string {
  if (!p || typeof p !== 'object') return ''
  const stage = String(p.stage ?? '')
  if (stage === 'gmail_progress') {
    const phase =
      p.phase === 'gyb'
        ? 'Descargando correo desde Gmail (GYB) al servidor'
        : 'Importando mensajes al buzón local Maildir (el que ve Dovecot/Roundcube)'
    const parts: string[] = []
    if (typeof p.messages === 'number') parts.push(`~${p.messages} mensajes (estimado en vivo)`)
    if (typeof p.files === 'number') parts.push(`${p.files} archivos`)
    if (typeof p.bytes === 'number') parts.push(humanBytes(p.bytes))
    const extra = parts.length ? ` · ${parts.join(' · ')}` : ''
    return `${phase}${extra}.`
  }
  if (stage === 'vault_push') {
    const sub = typeof p.subpath === 'string' ? p.subpath : '1-GMAIL/…'
    return `Subiendo el export a la bóveda de Google Drive del usuario (ruta relativa: ${sub}).`
  }
  if (stage === 'vault_ensure_dest') {
    const sub = typeof p.subpath === 'string' ? p.subpath : '1-GMAIL/…'
    return `Comprobando o recreando la carpeta en el vault antes de subir (${sub}).`
  }
  if (stage === 'gyb_workdir_purge') {
    return 'Vaciando el directorio de trabajo GYB en el servidor tras verificar la subida a Drive.'
  }
  if (stage === 'start') {
    const sc = String(p.scope ?? '')
    if (sc === 'gmail') return 'Iniciando el job de Gmail (preparación y GYB)…'
    if (sc === 'drive_root' || sc === 'drive_computadoras') return 'Iniciando copia/sincronización de Google Drive…'
    return `Iniciando (${sc})…`
  }
  if (stage === 'progress') {
    const raw = typeof p.raw === 'string' ? p.raw.trim() : ''
    if (raw) {
      return `Drive (rclone): ${raw.slice(0, 280)}${raw.length > 280 ? '…' : ''}`
    }
    return 'Copiando o sincronizando archivos de Google Drive (rclone)…'
  }
  if (stage === 'retention') return 'Aplicando retención en snapshots de Drive después del backup.'
  if (stage === 'retention_warning') return 'Aviso durante retención de Drive (revisá logs del worker si persiste).'
  if (stage === 'worker_skipped') return 'Omitido: ya había otro backup activo para esta cuenta y alcance.'
  if (stage === 'gyb_done') return 'GYB terminó la descarga; sigue la importación al buzón Maildir local.'
  if (stage === 'maildir_ready')
    return 'Buzón local listo: ya podés revisar correo en el visor / IMAP mientras continúa la subida al vault (si aplica).'
  if (stage === 'vault_push_retry') return 'Reintentando solo la subida del export a la bóveda Google (1-GMAIL/…)…'
  if (stage === 'cancelled') return 'Cancelación registrada.'
  if (stage === 'failed') return 'El worker reportó un fallo en esta fase (ver detalle abajo si hay traza).'
  if (stage === 'done') return 'El worker marcó paso «done»; el log puede tardar un momento en pasar a exitoso.'
  return `Etapa: ${stage}`
}

/** Ayuda a diagnosticar fallos del GET /backup/logs/:id */
function ExecutionDetailError({ err }: { err: unknown }) {
  const ax = err as AxiosError<{ detail?: unknown }> | undefined
  const st = ax?.response?.status
  const d = ax?.response?.data?.detail
  if (st === 404) return <p className="text-slate-600 dark:text-slate-400">El log no existe o fue eliminado.</p>
  if (st === 403) return <p className="text-slate-600 dark:text-slate-400">Sin permiso para ver logs (logs.view).</p>
  if (st === 401) return <p className="text-slate-600 dark:text-slate-400">Sesión expirada; volvé a iniciar sesión.</p>
  if (st === 502 || st === 503)
    return <p className="text-slate-600 dark:text-slate-400">API o proxy no disponible (502/503).</p>
  if (typeof d === 'string')
    return (
      <p className="font-mono text-xs break-all text-slate-700 dark:text-slate-300 bg-slate-100 dark:bg-slate-900 p-2 rounded">
        {d}
      </p>
    )
  if (d && typeof d === 'object' && 'error' in d) {
    const o = d as { error?: string }
    if (o.error)
      return (
        <p className="font-mono text-xs break-all text-slate-700 dark:text-slate-300 bg-slate-100 dark:bg-slate-900 p-2 rounded">
          {o.error}
        </p>
      )
  }
  if (st) return <p className="text-xs text-slate-500">Código HTTP {st}</p>
  if (ax?.code === 'ECONNABORTED') return <p className="text-xs text-slate-500">Tiempo de espera agotado.</p>
  if (ax?.message) return <p className="text-xs text-slate-500">{ax.message}</p>
  return null
}

/** Alcance y modo de ejecución legibles en la UI */
function taskTypeLabel(scope: string, mode: string): string {
  const scopePart =
    scope === 'gmail'
      ? 'Gmail'
      : scope === 'drive_root' || scope === 'drive_computadoras'
        ? 'Drive'
        : scope === 'full'
          ? 'Completo (Drive + Gmail)'
          : scope
  const modePart = mode === 'incremental' ? 'incremental' : mode === 'full' ? 'completo' : mode
  return `${scopePart} · ${modePart}`
}

/** Reintento solo de rclone al vault (1-GMAIL); requiere export GYB aún en disco. */
function canRetryGmailVault(log: BackupLog): boolean {
  if (log.scope !== 'gmail') return false
  if (!log.gmail_maildir_ready_at) return false
  if (log.gmail_vault_completed_at) return false
  if (log.status !== 'failed' && log.status !== 'cancelled') return false
  return true
}

export default function LogsPage() {
  const [status, setStatus] = useState<string>('')
  const { data: profile } = useProfile()
  const perms = new Set(profile?.permissions ?? [])
  const canExportPdf = perms.has('logs.export')
  const canDeleteLogs = perms.has('logs.delete')

  const { data = [], isLoading } = useBackupLogs({ status: status || undefined })
  const cancelLog = useCancelBackupLog()
  const cancelBatch = useCancelBackupBatch()
  const retryGmailVault = useRetryGmailVault()
  const deleteLog = useDeleteBackupLog()
  const deleteBulk = useDeleteBackupLogsBulk()

  const [confirmLog, setConfirmLog] = useState<BackupLog | null>(null)
  const [detailId, setDetailId] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<BackupLog | null>(null)
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false)
  const [pdfBusy, setPdfBusy] = useState(false)
  const detailQuery = useBackupLogDetail(detailId)

  const deletableVisibleCount = data.filter((l) => l.status !== 'running').length

  async function doCancelThisOnly(log: BackupLog) {
    try {
      await cancelLog.mutateAsync(log.id)
      toast.success('Backup de esta cuenta cancelado')
    } catch {
      toast.error('No se pudo cancelar')
    } finally {
      setConfirmLog(null)
    }
  }

  async function doCancelEntireBatch(log: BackupLog) {
    if (!log.run_batch_id) return
    try {
      const r = await cancelBatch.mutateAsync(log.run_batch_id)
      toast.success(
        `Lote cancelado: ${r.cancelled_logs} log(s), ${r.revoked_celery} job(s) Celery revocados`,
      )
    } catch {
      toast.error('No se pudo cancelar el lote')
    } finally {
      setConfirmLog(null)
    }
  }

  function onClickCancel(log: BackupLog) {
    if (log.status !== 'running') return
    if (log.run_batch_id) {
      setConfirmLog(log)
      return
    }
    void doCancelThisOnly(log)
  }

  async function doDeleteOne(log: BackupLog) {
    try {
      await deleteLog.mutateAsync(log.id)
      toast.success('Registro eliminado del historial')
      if (detailId === log.id) setDetailId(null)
    } catch {
      toast.error('No se pudo eliminar (¿en ejecución o sin permiso?)')
    } finally {
      setDeleteTarget(null)
    }
  }

  async function doBulkDeleteVisible() {
    const ids = data.filter((l) => l.status !== 'running').map((l) => l.id)
    if (!ids.length) {
      toast.error('No hay filas eliminables (en ejecución se omiten)')
      setBulkDeleteOpen(false)
      return
    }
    try {
      const r = await deleteBulk.mutateAsync(ids)
      if (r.deleted > 0) toast.success(`Eliminados: ${r.deleted}`)
      if (r.skipped_running.length)
        toast(`${r.skipped_running.length} en ejecución omitidos`, { icon: 'ℹ️' })
      if (r.not_found.length) toast(`Algunos IDs ya no existían (${r.not_found.length})`, { icon: '⚠️' })
      if (detailId && ids.includes(detailId)) setDetailId(null)
    } catch {
      toast.error('No se pudo eliminar el listado')
    } finally {
      setBulkDeleteOpen(false)
    }
  }

  async function handleExportPdf() {
    setPdfBusy(true)
    try {
      await downloadBackupLogsPdf({ status: status || undefined })
      toast.success('PDF generado')
    } catch {
      toast.error('No se pudo exportar el PDF')
    } finally {
      setPdfBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Historial de ejecuciones</h1>
        <p className="text-slate-500">
          Hacé clic en una fila para ver el detalle completo (IDs, rutas, error del servidor).
          Podés cancelar una cuenta en curso o todo el lote desde el botón de la fila; eliminar filas
          finalizadas con la X; exportar el listado actual a PDF o borrar en bloque las filas visibles
          (no borra ejecuciones «running»).
        </p>
      </div>
      <Card>
        <div className="flex gap-3 flex-wrap items-center">
          <Select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">Todos los estados</option>
            <option value="running">En ejecución</option>
            <option value="success">Exitosos</option>
            <option value="failed">Fallidos</option>
            <option value="cancelled">Cancelados</option>
          </Select>
          {canExportPdf ? (
            <Button color="light" size="sm" disabled={pdfBusy} onClick={() => void handleExportPdf()}>
              <HiDownload className="h-4 w-4 mr-1 inline" />
              {pdfBusy ? 'Exportando…' : 'Exportar PDF'}
            </Button>
          ) : null}
          {canDeleteLogs ? (
            <Button
              color="failure"
              outline
              size="sm"
              disabled={deleteBulk.isPending || !data.length || deletableVisibleCount === 0}
              onClick={() => setBulkDeleteOpen(true)}
            >
              <HiTrash className="h-4 w-4 mr-1 inline" />
              Eliminar listado visible
            </Button>
          ) : null}
        </div>
      </Card>
      <Card>
        {isLoading ? (
          <p className="text-slate-500">Cargando…</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="text-left text-slate-500">
                <tr>
                  <th className="py-2">Inicio</th>
                  <th>Fin</th>
                  <th>Cuenta</th>
                  <th>Tarea</th>
                  <th>Tipo</th>
                  <th>Lote</th>
                  <th>Estado</th>
                  <th>Bytes</th>
                  <th>Mensajes</th>
                  <th>Errores</th>
                  <th>Motivo / detalle</th>
                  <th className="text-right w-36">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {data.map((l) => (
                  <tr
                    key={l.id}
                    role="button"
                    tabIndex={0}
                    className="border-t border-slate-100 dark:border-slate-800 cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/60"
                    onClick={() => setDetailId(l.id)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault()
                        setDetailId(l.id)
                      }
                    }}
                  >
                    <td className="py-2">{l.started_at ?? '—'}</td>
                    <td>{l.finished_at ?? '—'}</td>
                    <td className="max-w-[14rem] truncate text-xs" title={l.account_email ?? l.account_id}>
                      {l.account_email ?? `${l.account_id.slice(0, 8)}…`}
                    </td>
                    <td className="max-w-[12rem] truncate text-xs" title={l.task_name ?? l.task_id}>
                      {l.task_name ?? `${l.task_id.slice(0, 8)}…`}
                    </td>
                    <td className="text-xs text-slate-600 dark:text-slate-400 whitespace-nowrap">
                      {taskTypeLabel(l.scope, l.mode)}
                    </td>
                    <td className="text-xs font-mono">
                      {l.run_batch_id ? `${l.run_batch_id.slice(0, 8)}…` : '—'}
                    </td>
                    <td>
                      <Badge
                        color={
                          l.status === 'success'
                            ? 'success'
                            : l.status === 'failed'
                              ? 'failure'
                              : l.status === 'running'
                                ? 'info'
                                : 'gray'
                        }
                      >
                        {l.status}
                      </Badge>
                    </td>
                    <td>{humanBytes(l.bytes_transferred)}</td>
                    <td>{l.messages_count}</td>
                    <td>{l.errors_count}</td>
                    <td
                      className="max-w-[220px] text-xs text-slate-600 dark:text-slate-400 align-top"
                      title={l.error_summary ?? undefined}
                    >
                      {l.status === 'failed' && !l.error_summary?.trim()
                        ? 'Sin texto (ver logs del worker: msa-backup-worker)'
                        : truncateDetail(l.error_summary)}
                    </td>
                    <td className="text-right align-middle">
                      <div className="flex justify-end items-center gap-1 flex-wrap">
                        {l.status === 'running' ? (
                          <Button
                            size="xs"
                            color="failure"
                            disabled={cancelLog.isPending || cancelBatch.isPending}
                            onClick={(e) => {
                              e.stopPropagation()
                              onClickCancel(l)
                            }}
                          >
                            Cancelar
                          </Button>
                        ) : null}
                        {canDeleteLogs && l.status !== 'running' ? (
                          <button
                            type="button"
                            className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/40 border border-red-200 dark:border-red-900/60"
                            title="Eliminar este registro del historial"
                            disabled={deleteLog.isPending}
                            onClick={(e) => {
                              e.stopPropagation()
                              setDeleteTarget(l)
                            }}
                          >
                            <HiX className="h-5 w-5" aria-hidden />
                            <span className="sr-only">Eliminar log</span>
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Modal show={detailId !== null} onClose={() => setDetailId(null)} size="xl">
        <Modal.Header>Detalle de ejecución</Modal.Header>
        <Modal.Body className="space-y-4 max-h-[75vh] overflow-y-auto">
          {detailQuery.isLoading ? (
            <p className="text-slate-500">Cargando…</p>
          ) : detailQuery.isError ? (
            <div className="text-red-600 text-sm space-y-1">
              <p>No se pudo cargar el detalle. Reintentá.</p>
              <ExecutionDetailError err={detailQuery.error} />
            </div>
          ) : detailQuery.data ? (
            <>
              <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50/80 dark:bg-slate-800/40 p-4 space-y-2">
                <div>
                  <div className="text-xs font-medium uppercase tracking-wide text-slate-500">Cuenta</div>
                  <div className="text-base font-semibold text-slate-900 dark:text-white break-all">
                    {detailQuery.data.account_email ?? '—'}
                  </div>
                  <div className="font-mono text-[11px] text-slate-500 break-all">{detailQuery.data.account_id}</div>
                </div>
                <div>
                  <div className="text-xs font-medium uppercase tracking-wide text-slate-500">Tarea en ejecución</div>
                  <div className="text-base font-semibold text-slate-900 dark:text-white">
                    {detailQuery.data.task_name ?? '—'}
                  </div>
                  <div className="text-sm text-slate-600 dark:text-slate-400">
                    {taskTypeLabel(detailQuery.data.scope, detailQuery.data.mode)}
                  </div>
                  <div className="font-mono text-[11px] text-slate-500 break-all">{detailQuery.data.task_id}</div>
                </div>
              </div>

              {detailQuery.data.status === 'running' ? (
                <div className="rounded-lg border border-blue-200 dark:border-blue-900/50 bg-blue-50/70 dark:bg-blue-950/25 p-4">
                  <div className="text-xs font-semibold uppercase tracking-wide text-blue-800 dark:text-blue-300">
                    Qué está haciendo ahora
                  </div>
                  <p className="text-sm text-slate-800 dark:text-slate-200 mt-2 leading-relaxed">
                    {describeLiveProgress(detailQuery.data.live_progress ?? null) ||
                      'Todavía no llegó telemetría al panel (esperá unos segundos). Si persiste, comprobá Redis y el worker.'}
                  </p>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-2">
                    Gmail suele pasar por: <strong>GYB</strong> (descarga) → <strong>Maildir</strong> (importación
                    local) → opcionalmente <strong>subida a la bóveda</strong> (1-GMAIL en Drive). El detalle se
                    actualiza solo mientras el estado es «running» (refresco ~3 s).
                  </p>
                  {detailQuery.data.live_progress && Object.keys(detailQuery.data.live_progress).length > 0 ? (
                    <details className="mt-3 text-xs">
                      <summary className="cursor-pointer text-slate-600 dark:text-slate-400 select-none">
                        Último evento (JSON)
                      </summary>
                      <pre className="mt-2 whitespace-pre-wrap break-all bg-slate-100 dark:bg-slate-900 p-2 rounded border border-slate-200 dark:border-slate-700 max-h-44 overflow-y-auto font-mono">
                        {JSON.stringify(detailQuery.data.live_progress, null, 2)}
                      </pre>
                    </details>
                  ) : null}
                </div>
              ) : null}

              <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2 text-sm">
                <div>
                  <dt className="text-slate-500">ID del log</dt>
                  <dd className="font-mono text-xs break-all">{detailQuery.data.id}</dd>
                </div>
                <div>
                  <dt className="text-slate-500">Estado</dt>
                  <dd>
                    <Badge
                      color={
                        detailQuery.data.status === 'success'
                          ? 'success'
                          : detailQuery.data.status === 'failed'
                            ? 'failure'
                            : detailQuery.data.status === 'running'
                              ? 'info'
                              : 'gray'
                      }
                    >
                      {detailQuery.data.status}
                    </Badge>
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500">Lote (run_batch_id)</dt>
                  <dd className="font-mono text-xs break-all">
                    {detailQuery.data.run_batch_id ?? '—'}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500">Celery task id</dt>
                  <dd className="font-mono text-xs break-all">
                    {detailQuery.data.celery_task_id ?? '—'}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500">Pipeline Gmail (local / vault)</dt>
                  <dd className="text-xs">
                    Maildir en BD: {detailQuery.data.gmail_maildir_ready_at ?? '—'}
                    <br />
                    Vault 1-GMAIL: {detailQuery.data.gmail_vault_completed_at ?? '—'}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500">Scope / modo (técnico)</dt>
                  <dd>
                    {detailQuery.data.scope} · {detailQuery.data.mode}
                  </dd>
                </div>
                {detailQuery.data.scope === 'gmail' ? (
                  <div className="sm:col-span-2 rounded-lg bg-slate-50 dark:bg-slate-800/50 p-3 text-xs text-slate-600 dark:text-slate-400">
                    <strong>Gmail:</strong> GYB guarda <code>.eml</code> en el servidor y la plataforma los
                    importa a <strong>Maildir</strong> (ruta destino); Roundcube lee eso, no la carpeta
                    «Gmail» de Drive. Si antes veías 0 mensajes con éxito, actualizá el worker: la importación
                    antigua solo buscaba <code>.mbox</code>. Con el job <strong>en ejecución</strong>, los
                    contadores se actualizan cada pocos segundos: fase <em>export</em> (archivos GYB) y luego{' '}
                    <em>import</em> (Maildir); al final se fijan los totales definitivos.
                  </div>
                ) : null}
                <div>
                  <dt className="text-slate-500">Inicio / fin</dt>
                  <dd className="text-xs">
                    {detailQuery.data.started_at ?? '—'}
                    <br />
                    {detailQuery.data.finished_at ?? '—'}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500">Bytes / archivos / mensajes / errores (contador)</dt>
                  <dd>
                    {humanBytes(detailQuery.data.bytes_transferred)} · {detailQuery.data.files_count}{' '}
                    arch. · {detailQuery.data.messages_count} msg. · {detailQuery.data.errors_count}{' '}
                    err.
                  </dd>
                </div>
                <div className="sm:col-span-2">
                  <dt className="text-slate-500">Informe en vault (3-REPORTS)</dt>
                  <dd className="font-mono text-xs break-all">
                    {detailQuery.data.detail_log_path ?? '—'}
                  </dd>
                </div>
                <div className="sm:col-span-2">
                  <dt className="text-slate-500">Ruta destino</dt>
                  <dd className="font-mono text-xs break-all">
                    {detailQuery.data.destination_path ?? '—'}
                  </dd>
                </div>
                <div className="sm:col-span-2">
                  <dt className="text-slate-500">Manifiesto SHA-256</dt>
                  <dd className="font-mono text-xs break-all">
                    {detailQuery.data.sha256_manifest_path ?? '—'}
                  </dd>
                </div>
              </dl>
              <div>
                <div className="text-sm text-slate-500 mb-1">Motivo / traza del servidor</div>
                <pre className="text-xs whitespace-pre-wrap break-words bg-slate-100 dark:bg-slate-900 text-slate-800 dark:text-slate-200 rounded-lg p-3 max-h-64 overflow-y-auto border border-slate-200 dark:border-slate-700">
                  {detailQuery.data.error_summary?.trim()
                    ? detailQuery.data.error_summary
                    : '— (sin mensaje; si falló Gmail, revisá que la imagen del worker tenga GYB y reconstruyá con docker compose build --no-cache worker)'}
                </pre>
              </div>
            </>
          ) : null}
        </Modal.Body>
        <Modal.Footer className="flex flex-wrap gap-2 justify-end">
          {detailQuery.data && canRetryGmailVault(detailQuery.data) ? (
            <Button
              color="blue"
              disabled={retryGmailVault.isPending}
              onClick={() => {
                void (async () => {
                  try {
                    const r = await retryGmailVault.mutateAsync(detailQuery.data!.id)
                    toast.success(`Reintento encolado (Celery ${r.celery_id.slice(0, 8)}…)`)
                  } catch {
                    toast.error('No se pudo encolar el reintento (¿workdir GYB vacío u otro backup activo?)')
                  }
                })()
              }}
            >
              Reintentar subida al vault
            </Button>
          ) : null}
          <Button color="gray" onClick={() => setDetailId(null)}>
            Cerrar
          </Button>
        </Modal.Footer>
      </Modal>

      <Modal show={confirmLog !== null} onClose={() => setConfirmLog(null)} size="md">
        <Modal.Header>¿Cómo cancelar?</Modal.Header>
        <Modal.Body>
          <p className="text-sm text-slate-600 dark:text-slate-400 mb-3">
            Este backup pertenece a un <strong>lote</strong> (varias cuentas o Gmail+Drive). Podés
            parar solo esta ejecución y dejar seguir las demás, o frenar todo el lote (revoca jobs en
            cola y corta las que siguen en curso).
          </p>
        </Modal.Body>
        <Modal.Footer>
          <Button
            color="light"
            onClick={() => confirmLog && void doCancelThisOnly(confirmLog)}
            disabled={cancelLog.isPending}
          >
            Solo esta cuenta
          </Button>
          <Button
            color="failure"
            onClick={() => confirmLog && void doCancelEntireBatch(confirmLog)}
            disabled={cancelBatch.isPending}
          >
            Detener todo el lote
          </Button>
          <Button color="gray" onClick={() => setConfirmLog(null)}>
            Volver
          </Button>
        </Modal.Footer>
      </Modal>
      <Modal show={bulkDeleteOpen} onClose={() => setBulkDeleteOpen(false)} size="md">
        <Modal.Header>Eliminar historial visible</Modal.Header>
        <Modal.Body>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            Se eliminarán{' '}
            <strong>{deletableVisibleCount}</strong> registro(s) que aparecen
            en la tabla con el filtro actual. Las ejecuciones en curso («running») no se borran.
          </p>
        </Modal.Body>
        <Modal.Footer>
          <Button color="failure" disabled={deleteBulk.isPending} onClick={() => void doBulkDeleteVisible()}>
            Confirmar eliminación
          </Button>
          <Button color="gray" onClick={() => setBulkDeleteOpen(false)}>
            Cancelar
          </Button>
        </Modal.Footer>
      </Modal>

      <Modal show={deleteTarget !== null} onClose={() => setDeleteTarget(null)} size="md">
        <Modal.Header>Eliminar registro</Modal.Header>
        <Modal.Body>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            ¿Eliminar del historial la ejecución de{' '}
            <strong>{deleteTarget?.account_email ?? deleteTarget?.account_id?.slice(0, 8)}</strong> del{' '}
            <strong>{deleteTarget?.started_at ?? '—'}</strong>? Esta acción no revierte backups ya hechos.
          </p>
        </Modal.Body>
        <Modal.Footer>
          <Button
            color="failure"
            disabled={deleteLog.isPending}
            onClick={() => deleteTarget && void doDeleteOne(deleteTarget)}
          >
            Eliminar
          </Button>
          <Button color="gray" onClick={() => setDeleteTarget(null)}>
            Volver
          </Button>
        </Modal.Footer>
      </Modal>
    </div>
  )
}
