import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Badge, Button, Card, Checkbox, Label, Modal, Select, TextInput } from 'flowbite-react'
import { HiSearch } from 'react-icons/hi'
import { useQuery } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import api from '../api/client'
import {
  useAccounts,
  useCreateUser,
  useMailboxDelegations,
  usePlatformRoles,
  usePutMailboxDelegations,
  useUpdateUser,
} from '../api/hooks'
import type { WorkspaceAccount } from '../api/types'
import { useAuthStore } from '../stores/auth'

interface UserRow {
  id: string
  email: string
  full_name: string
  role_code: string
  role_name?: string | null
  status: string
  mfa_enabled: boolean
  last_login_at: string | null
}

function roleBadgeColor(code: string): 'failure' | 'info' | 'gray' | 'success' {
  if (code === 'super_admin') return 'failure'
  if (code === 'operator') return 'info'
  if (code === 'auditor') return 'gray'
  return 'success'
}

export default function UsersPage() {
  const hasPermission = useAuthStore((s) => s.hasPermission)
  const canDelegateMailbox = hasPermission('mailbox.delegate')
  const canCreate = hasPermission('users.create')
  const canEdit = hasPermission('users.edit')

  const { data: users = [], isLoading } = useQuery({
    queryKey: ['users'],
    queryFn: async () => (await api.get<UserRow[]>('/users')).data,
  })

  const rolesQ = usePlatformRoles()
  const roleOptions = rolesQ.data ?? []

  const { data: accounts = [] } = useAccounts(undefined)

  const createUserM = useCreateUser()
  const updateUserM = useUpdateUser()

  const [delegateUser, setDelegateUser] = useState<UserRow | null>(null)
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [accountSearch, setAccountSearch] = useState('')

  const [createOpen, setCreateOpen] = useState(false)
  const [cuEmail, setCuEmail] = useState('')
  const [cuName, setCuName] = useState('')
  const [cuPassword, setCuPassword] = useState('')
  const [cuRole, setCuRole] = useState('')
  const [cuMustChange, setCuMustChange] = useState(true)

  const [editUser, setEditUser] = useState<UserRow | null>(null)
  const [euName, setEuName] = useState('')
  const [euRole, setEuRole] = useState('')
  const [euStatus, setEuStatus] = useState('active')

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

  useEffect(() => {
    if (createOpen && roleOptions.length && !cuRole) {
      const aud = roleOptions.find((r) => r.code === 'auditor')
      setCuRole((aud ?? roleOptions[0])?.code ?? '')
    }
  }, [createOpen, roleOptions, cuRole])

  useEffect(() => {
    if (editUser) {
      setEuName(editUser.full_name)
      setEuRole(editUser.role_code)
      setEuStatus(editUser.status)
    }
  }, [editUser])

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
      toast.success('Delegaciones actualizadas (Maildir y bandejas GYB en esas cuentas)')
      setDelegateUser(null)
    } catch {
      toast.error('No se pudo guardar. Revisá permisos (mailbox.delegate) y consola de red.')
    }
  }

  async function submitCreate() {
    if (!cuRole) {
      toast.error('Elegí un rol')
      return
    }
    try {
      await createUserM.mutateAsync({
        email: cuEmail.trim().toLowerCase(),
        full_name: cuName.trim(),
        role_code: cuRole,
        password: cuPassword,
        must_change_password: cuMustChange,
      })
      toast.success('Usuario creado')
      setCreateOpen(false)
      setCuEmail('')
      setCuName('')
      setCuPassword('')
      setCuMustChange(true)
    } catch {
      toast.error('No se pudo crear (¿correo duplicado o contraseña corta?)')
    }
  }

  async function submitEdit() {
    if (!editUser) return
    try {
      await updateUserM.mutateAsync({
        userId: editUser.id,
        body: {
          full_name: euName.trim(),
          role_code: euRole,
          status: euStatus,
        },
      })
      toast.success('Usuario actualizado')
      setEditUser(null)
    } catch {
      toast.error('No se pudo guardar (¿permisos de super admin?)')
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Usuarios de la plataforma</h1>
          <p className="text-slate-500">
            Los <strong>roles</strong> definen permisos; para solo GYB sobre correos concretos usá un rol con{' '}
            <code className="text-xs">mailbox.view_delegated</code> y delegá cuentas aquí.{' '}
            <Link to="/roles" className="text-blue-600 dark:text-blue-400 hover:underline text-sm">
              Gestionar roles
            </Link>
          </p>
        </div>
        {canCreate ? (
          <Button onClick={() => setCreateOpen(true)}>Nuevo usuario</Button>
        ) : null}
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
                  {canDelegateMailbox ? <th className="text-right">Delegación</th> : null}
                  {canEdit ? <th className="text-right">Editar</th> : null}
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id} className="border-t border-slate-100 dark:border-slate-800">
                    <td className="py-2 font-medium">{u.email}</td>
                    <td>{u.full_name}</td>
                    <td>
                      <Badge color={roleBadgeColor(u.role_code)} title={u.role_name ?? u.role_code}>
                        {u.role_name ? `${u.role_name} · ${u.role_code}` : u.role_code}
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
                          Buzones
                        </Button>
                      </td>
                    ) : null}
                    {canEdit ? (
                      <td className="text-right">
                        <Button size="xs" color="light" onClick={() => setEditUser(u)}>
                          Editar
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

      <Modal show={createOpen} onClose={() => setCreateOpen(false)}>
        <Modal.Header>Nuevo usuario</Modal.Header>
        <Modal.Body className="space-y-3">
          <div>
            <Label value="Correo" />
            <TextInput type="email" value={cuEmail} onChange={(e) => setCuEmail(e.target.value)} />
          </div>
          <div>
            <Label value="Nombre completo" />
            <TextInput value={cuName} onChange={(e) => setCuName(e.target.value)} />
          </div>
          <div>
            <Label value="Contraseña inicial (mín. 12 caracteres)" />
            <TextInput type="password" value={cuPassword} onChange={(e) => setCuPassword(e.target.value)} />
          </div>
          <div>
            <Label value="Rol" />
            <Select value={cuRole} onChange={(e) => setCuRole(e.target.value)}>
              {roleOptions.map((r) => (
                <option key={r.id} value={r.code}>
                  {r.name} ({r.code})
                </option>
              ))}
            </Select>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <Checkbox checked={cuMustChange} onChange={(e) => setCuMustChange(e.target.checked)} />
            Debe cambiar la contraseña al entrar
          </label>
        </Modal.Body>
        <Modal.Footer>
          <Button color="gray" onClick={() => setCreateOpen(false)}>
            Cancelar
          </Button>
          <Button onClick={() => void submitCreate()} disabled={createUserM.isPending}>
            Crear
          </Button>
        </Modal.Footer>
      </Modal>

      <Modal show={!!editUser} onClose={() => setEditUser(null)}>
        <Modal.Header>Editar {editUser?.email ?? ''}</Modal.Header>
        <Modal.Body className="space-y-3">
          <div>
            <Label value="Nombre" />
            <TextInput value={euName} onChange={(e) => setEuName(e.target.value)} />
          </div>
          <div>
            <Label value="Rol" />
            <Select value={euRole} onChange={(e) => setEuRole(e.target.value)}>
              {roleOptions.map((r) => (
                <option key={r.id} value={r.code}>
                  {r.name} ({r.code})
                </option>
              ))}
            </Select>
          </div>
          <div>
            <Label value="Estado" />
            <Select value={euStatus} onChange={(e) => setEuStatus(e.target.value)}>
              <option value="active">active</option>
              <option value="suspended">suspended</option>
              <option value="pending_verification">pending_verification</option>
            </Select>
          </div>
        </Modal.Body>
        <Modal.Footer>
          <Button color="gray" onClick={() => setEditUser(null)}>
            Cancelar
          </Button>
          <Button onClick={() => void submitEdit()} disabled={updateUserM.isPending}>
            Guardar
          </Button>
        </Modal.Footer>
      </Modal>

      <Modal show={!!delegateUser} onClose={() => setDelegateUser(null)} size="xl">
        <Modal.Header>Buzones permitidos · {delegateUser?.email ?? ''}</Modal.Header>
        <Modal.Body>
          <p className="text-sm text-slate-500 mb-3">
            Marcá las cuentas que este usuario puede auditar con{' '}
            <code className="text-xs">mailbox.view_delegated</code> (Maildir, GYB trabajo y GYB en Drive).
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
