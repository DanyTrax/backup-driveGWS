import { Badge, Button, Card, Modal, Select } from 'flowbite-react'
import { useState } from 'react'
import toast from 'react-hot-toast'
import {
  useBackupLogDetail,
  useBackupLogs,
  useCancelBackupBatch,
  useCancelBackupLog,
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

export default function LogsPage() {
  const [status, setStatus] = useState<string>('')
  const { data = [], isLoading } = useBackupLogs({ status: status || undefined })
  const cancelLog = useCancelBackupLog()
  const cancelBatch = useCancelBackupBatch()

  const [confirmLog, setConfirmLog] = useState<BackupLog | null>(null)
  const [detailId, setDetailId] = useState<string | null>(null)
  const detailQuery = useBackupLogDetail(detailId)

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

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Historial de ejecuciones</h1>
        <p className="text-slate-500">
          Hacé clic en una fila para ver el detalle completo (IDs, rutas, error del servidor).
          Podés cancelar una cuenta en curso o todo el lote desde el botón de la fila.
        </p>
      </div>
      <Card>
        <div className="flex gap-3 flex-wrap">
          <Select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">Todos los estados</option>
            <option value="running">En ejecución</option>
            <option value="success">Exitosos</option>
            <option value="failed">Fallidos</option>
            <option value="cancelled">Cancelados</option>
          </Select>
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
                  <th>Tarea</th>
                  <th>Lote</th>
                  <th>Scope</th>
                  <th>Estado</th>
                  <th>Bytes</th>
                  <th>Mensajes</th>
                  <th>Errores</th>
                  <th>Motivo / detalle</th>
                  <th></th>
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
                    <td className="text-xs font-mono">{l.task_id.slice(0, 8)}…</td>
                    <td className="text-xs font-mono">
                      {l.run_batch_id ? `${l.run_batch_id.slice(0, 8)}…` : '—'}
                    </td>
                    <td>{l.scope}</td>
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
                    <td className="text-right">
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
            <p className="text-red-600">No se pudo cargar el detalle. Reintentá.</p>
          ) : detailQuery.data ? (
            <>
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
                  <dt className="text-slate-500">Tarea (task_id)</dt>
                  <dd className="font-mono text-xs break-all">{detailQuery.data.task_id}</dd>
                </div>
                <div>
                  <dt className="text-slate-500">Cuenta (account_id)</dt>
                  <dd className="font-mono text-xs break-all">{detailQuery.data.account_id}</dd>
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
                  <dt className="text-slate-500">Scope / modo</dt>
                  <dd>
                    {detailQuery.data.scope} · {detailQuery.data.mode}
                  </dd>
                </div>
                {detailQuery.data.scope === 'gmail' ? (
                  <div className="sm:col-span-2 rounded-lg bg-slate-50 dark:bg-slate-800/50 p-3 text-xs text-slate-600 dark:text-slate-400">
                    <strong>Gmail:</strong> GYB guarda <code>.eml</code> en el servidor y la plataforma los
                    importa a <strong>Maildir</strong> (ruta destino); Roundcube lee eso, no la carpeta
                    «Gmail» de Drive. Si antes veías 0 mensajes con éxito, actualizá el worker: la importación
                    antigua solo buscaba <code>.mbox</code>.
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
        <Modal.Footer>
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
    </div>
  )
}
