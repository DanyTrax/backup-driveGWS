import { Badge, Card } from 'flowbite-react'
import { useRestoreJobs } from '../api/hooks'

export default function RestorePage() {
  const { data = [], isLoading } = useRestoreJobs()

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Trabajos de restauración</h1>
        <p className="text-slate-500">Drive total, selectivo y Gmail granular</p>
      </div>
      <Card>
        {isLoading ? (
          <p className="text-slate-500">Cargando…</p>
        ) : data.length === 0 ? (
          <p className="text-slate-500">Aún no hay trabajos de restauración.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="text-left text-slate-500">
                <tr>
                  <th className="py-2">Creado</th>
                  <th>Cuenta</th>
                  <th>Alcance</th>
                  <th>Estado</th>
                  <th>Items</th>
                  <th>Errores</th>
                </tr>
              </thead>
              <tbody>
                {data.map((j) => (
                  <tr key={j.id} className="border-t border-slate-100 dark:border-slate-800">
                    <td className="py-2">{j.created_at}</td>
                    <td className="font-mono text-xs">{j.target_account_id.slice(0, 8)}</td>
                    <td>{j.scope}</td>
                    <td>
                      <Badge
                        color={
                          j.status === 'success'
                            ? 'success'
                            : j.status === 'failed'
                            ? 'failure'
                            : j.status === 'running'
                            ? 'info'
                            : 'gray'
                        }
                      >
                        {j.status}
                      </Badge>
                    </td>
                    <td>
                      {j.items_restored}/{j.items_total}
                    </td>
                    <td>{j.items_failed}</td>
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
