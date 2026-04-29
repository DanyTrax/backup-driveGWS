import { useEffect, useMemo, useState } from 'react'
import { Badge, Button, Card, Checkbox, Label, Modal, TextInput } from 'flowbite-react'
import { HiSearch } from 'react-icons/hi'
import { useQuery } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import api from '../api/client'
import {
  useAccounts,
  useMailboxDelegations,
  usePutMailboxDelegations,
} from '../api/hooks'
import type { WorkspaceAccount } from '../api/types'
import { useAuthStore } from '../stores/auth'

interface UserRow {
  id: string
  email: string
  full_name: string
  role_code: string
  status: string
  mfa_enabled: boolean
  last_login_at: string | null
}

export default function UsersPage() {
  const hasPermission = useAuthStore((s) => s.hasPermission)
  const canDelegateMailbox = hasPermission('mailbox.delegate')

  const { data: users = [], isLoading } = useQuery({
    queryKey: ['users'],
    queryFn: async () => (await api.get<UserRow[]>('/users')).data,
  })

  const { data: accounts = [] } = useAccounts(undefined)

  const [delegateUser, setDelegateUser] = useState<UserRow | null>(null)
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [accountSearch, setAccountSearch] = useState('')

  const delegationsQ = useMailboxDelegations(delegateUser?.id ?? null)
  const putDelegations = usePutMailboxDelegations()

  useEffect(() => {
    if (!delegateUser) {
      setPicked(new Set())
      return
    }
    const ids = delegationsQ.data ?? []
    setPicked(new Set(ids))
  }, [delegateUser, delegationsQ.data])

  const filteredAccounts = useMemo(() => {
    const term = accountSearch.trim().toLowerCase()
    if (!term) return accounts
    return accounts.filter(
      (a) =>
        a.email.toLowerCase().includes(term) ||
        (a.full_name ?? '').toLowerCase().includes(term),
    )
  }, [accounts, accountSearch])

  function toggleAccount(id: string) {
    setPicked((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function saveDelegations() {
    if (!delegateUser) return
    try {
      await putDelegations.mutateAsync({
        userId: delegateUser.id,
        accountIds: Array.from(picked),
      })
      toast.success('Delegaciones Maildir actualizadas')
      setDelegateUser(null)
    } catch {
      toast.error('No se pudo guardar. Revisá permisos (mailbox.delegate) y consola de red.')
    }
  }

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
                  {canDelegateMailbox ? <th className="text-right">Maildir</th> : null}
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
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
                    {canDelegateMailbox ? (
                      <td className="text-right">
                        <Button size="xs" color="light" onClick={() => setDelegateUser(u)}>
                          Delegar buzones
                        </Button>
                      </td>
                    ) : null}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Modal show={!!delegateUser} onClose={() => setDelegateUser(null)} size="xl">
        <Modal.Header>
          Buzones Maildir para {delegateUser?.email ?? ''}
        </Modal.Header>
        <Modal.Body>
          <p className="text-sm text-slate-500 mb-3">
            Marcá las cuentas de Workspace cuyo Maildir puede auditar este usuario (requiere rol con{' '}
            <code className="text-xs">mailbox.view_delegated</code>).
          </p>
          <div className="mb-3">
            <Label value="Buscar cuenta" />
            <TextInput
              icon={HiSearch}
              value={accountSearch}
              onChange={(e) => setAccountSearch(e.target.value)}
              placeholder="Correo o nombre"
            />
          </div>
          <div className="max-h-72 overflow-y-auto border border-slate-200 dark:border-slate-700 rounded-lg p-2 space-y-2">
            {delegationsQ.isLoading ? (
              <p className="text-slate-500 text-sm">Cargando delegaciones…</p>
            ) : (
              filteredAccounts.map((a: WorkspaceAccount) => (
                <label
                  key={a.id}
                  className="flex items-center gap-2 text-sm cursor-pointer py-1 px-1 rounded hover:bg-slate-50 dark:hover:bg-slate-800"
                >
                  <Checkbox checked={picked.has(a.id)} onChange={() => toggleAccount(a.id)} />
                  <span className="font-medium">{a.email}</span>
                  <span className="text-slate-500 text-xs truncate">{a.full_name ?? ''}</span>
                </label>
              ))
            )}
          </div>
        </Modal.Body>
        <Modal.Footer>
          <Button color="gray" onClick={() => setDelegateUser(null)}>
            Cancelar
          </Button>
          <Button onClick={() => void saveDelegations()} disabled={putDelegations.isPending}>
            Guardar
          </Button>
        </Modal.Footer>
      </Modal>
    </div>
  )
}
