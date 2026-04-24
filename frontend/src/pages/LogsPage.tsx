import { Badge, Button, Card, Modal, Select } from 'flowbite-react'
import { useState } from 'react'
import toast from 'react-hot-toast'
import {
  useBackupLogs,
  useCancelBackupBatch,
  useCancelBackupLog,
} from '../api/hooks'
import type { BackupLog } from '../api/types'

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
          Cancelá una cuenta en curso o todo el lote (mismo disparo manual o programado).
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
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {data.map((l) => (
                  <tr key={l.id} className="border-t border-slate-100 dark:border-slate-800">
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
                    <td className="text-right">
                      {l.status === 'running' ? (
                        <Button
                          size="xs"
                          color="failure"
                          disabled={cancelLog.isPending || cancelBatch.isPending}
                          onClick={() => onClickCancel(l)}
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
