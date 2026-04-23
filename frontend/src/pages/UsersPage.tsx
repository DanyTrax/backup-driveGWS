import { Badge, Card } from 'flowbite-react'
import { useQuery } from '@tanstack/react-query'
import api from '../api/client'

interface User {
  id: string
  email: string
  full_name: string
  role_code: string
  status: string
  mfa_enabled: boolean
  last_login_at: string | null
}

export default function UsersPage() {
  const { data = [], isLoading } = useQuery({
    queryKey: ['users'],
    queryFn: async () => (await api.get<User[]>('/users')).data,
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Usuarios de la plataforma</h1>
        <p className="text-slate-500">Administradores, operadores y auditores</p>
      </div>
      <Card>
        {isLoading ? (
          <p className="text-slate-500">Cargando…</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="text-left text-slate-500">
                <tr>
                  <th className="py-2">Correo</th>
                  <th>Nombre</th>
                  <th>Rol</th>
                  <th>Estado</th>
                  <th>MFA</th>
                  <th>Último login</th>
                </tr>
              </thead>
              <tbody>
                {data.map((u) => (
                  <tr key={u.id} className="border-t border-slate-100 dark:border-slate-800">
                    <td className="py-2 font-medium">{u.email}</td>
                    <td>{u.full_name}</td>
                    <td>
                      <Badge
                        color={
                          u.role_code === 'super_admin'
                            ? 'failure'
                            : u.role_code === 'operator'
                            ? 'info'
                            : 'gray'
                        }
                      >
                        {u.role_code}
                      </Badge>
                    </td>
                    <td>{u.status}</td>
                    <td>
                      {u.mfa_enabled ? (
                        <Badge color="success">activo</Badge>
                      ) : (
                        <Badge color="gray">inactivo</Badge>
                      )}
                    </td>
                    <td className="text-xs text-slate-500">{u.last_login_at ?? '—'}</td>
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
