import { Badge, Button, Card } from 'flowbite-react'
import { HiPlay } from 'react-icons/hi'
import toast from 'react-hot-toast'
import { useRunTask, useTasks } from '../api/hooks'

export default function TasksPage() {
  const { data: tasks = [], isLoading } = useTasks()
  const run = useRunTask()

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Tareas de backup</h1>
          <p className="text-slate-500">Programa y ejecuta backups de Drive y Gmail</p>
        </div>
      </div>

      <Card>
        {isLoading ? (
          <p className="text-slate-500">Cargando…</p>
        ) : tasks.length === 0 ? (
          <p className="text-slate-500">Aún no hay tareas. Crea una desde la API o el asistente.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="text-left text-slate-500">
                <tr>
                  <th className="py-2">Nombre</th>
                  <th>Scope</th>
                  <th>Modo</th>
                  <th>Programación</th>
                  <th>Cuentas</th>
                  <th>Estado</th>
                  <th>Último run</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {tasks.map((t) => (
                  <tr key={t.id} className="border-t border-slate-100 dark:border-slate-800">
                    <td className="py-2 font-medium">{t.name}</td>
                    <td>{t.scope}</td>
                    <td>{t.mode}</td>
                    <td className="text-xs">
                      {t.schedule_kind === 'daily'
                        ? `Diario ${String(t.run_at_hour ?? 0).padStart(2, '0')}:${String(
                            t.run_at_minute ?? 0,
                          ).padStart(2, '0')}`
                        : t.schedule_kind === 'custom_cron'
                        ? t.cron_expression
                        : t.schedule_kind}
                    </td>
                    <td>{t.account_ids.length}</td>
                    <td>
                      {t.is_enabled ? (
                        <Badge color="success">activa</Badge>
                      ) : (
                        <Badge color="gray">pausada</Badge>
                      )}
                    </td>
                    <td className="text-xs text-slate-500">{t.last_run_at ?? '—'}</td>
                    <td className="text-right">
                      <Button
                        size="xs"
                        onClick={() =>
                          run.mutate(t.id, {
                            onSuccess: (data) =>
                              toast.success(`${data.queued} jobs en cola`),
                            onError: () => toast.error('No se pudo encolar'),
                          })
                        }
                      >
                        <HiPlay className="h-4 w-4 mr-1" /> Ejecutar
                      </Button>
                    </td>
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
