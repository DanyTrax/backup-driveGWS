import { Card } from 'flowbite-react'
import { HiCheckCircle, HiExclamation, HiUserGroup, HiClock } from 'react-icons/hi'
import { useAccounts, useBackupLogs, useTasks } from '../api/hooks'

export default function DashboardPage() {
  const { data: accounts = [] } = useAccounts()
  const { data: tasks = [] } = useTasks()
  const { data: logs = [] } = useBackupLogs()

  const enabled = accounts.filter((a) => a.is_backup_enabled)
  const running = logs.filter((l) => l.status === 'running').length
  const succeeded = logs.filter((l) => l.status === 'success').length
  const failed = logs.filter((l) => l.status === 'failed').length

  const stats = [
    { label: 'Cuentas con backup', value: `${enabled.length}/${accounts.length}`, icon: HiUserGroup, color: 'text-blue-500' },
    { label: 'Tareas definidas', value: tasks.length, icon: HiCheckCircle, color: 'text-green-500' },
    { label: 'En ejecución', value: running, icon: HiClock, color: 'text-amber-500' },
    { label: 'Completadas', value: succeeded, icon: HiCheckCircle, color: 'text-green-600' },
    { label: 'Errores recientes', value: failed, icon: HiExclamation, color: 'text-red-500' },
  ]

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-800 dark:text-white">Panel general</h1>
        <p className="text-slate-500">Estado del sistema en tiempo real</p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map(({ label, value, icon: Icon, color }) => (
          <Card key={label}>
            <div className="flex items-center gap-4">
              <Icon className={`h-10 w-10 ${color}`} />
              <div>
                <div className="text-sm text-slate-500">{label}</div>
                <div className="text-2xl font-semibold">{value}</div>
              </div>
            </div>
          </Card>
        ))}
      </div>

      <Card>
        <h2 className="text-lg font-semibold mb-4">Últimas ejecuciones</h2>
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="text-left text-slate-500">
              <tr>
                <th className="py-2">Tarea</th>
                <th>Cuenta</th>
                <th>Scope</th>
                <th>Estado</th>
                <th>Inicio</th>
              </tr>
            </thead>
            <tbody>
              {logs.slice(0, 20).map((l) => (
                <tr key={l.id} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="py-2 font-mono text-xs">{l.task_id.slice(0, 8)}</td>
                  <td className="font-mono text-xs">{l.account_id.slice(0, 8)}</td>
                  <td>{l.scope}</td>
                  <td>
                    <span className={
                      l.status === 'success'
                        ? 'text-green-600'
                        : l.status === 'failed'
                        ? 'text-red-600'
                        : l.status === 'running'
                        ? 'text-blue-600'
                        : 'text-slate-500'
                    }>
                      {l.status}
                    </span>
                  </td>
                  <td>{l.started_at ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
