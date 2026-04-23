import { Badge, Card, Select } from 'flowbite-react'
import { useState } from 'react'
import { useBackupLogs } from '../api/hooks'

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
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Historial de ejecuciones</h1>
        <p className="text-slate-500">Auditable y exportable</p>
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
                  <th>Scope</th>
                  <th>Estado</th>
                  <th>Bytes</th>
                  <th>Mensajes</th>
                  <th>Errores</th>
                </tr>
              </thead>
              <tbody>
                {data.map((l) => (
                  <tr key={l.id} className="border-t border-slate-100 dark:border-slate-800">
                    <td className="py-2">{l.started_at ?? '—'}</td>
                    <td>{l.finished_at ?? '—'}</td>
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
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
