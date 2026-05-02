import { useMemo, useState } from 'react'
import { Badge, Button, Card, Checkbox, Label, Modal, TextInput } from 'flowbite-react'
import toast from 'react-hot-toast'
import {
  useCreatePlatformRole,
  useDeletePlatformRole,
  usePermissionCatalog,
  usePlatformRoles,
  useUpdatePlatformRole,
} from '../api/hooks'
import type { PermissionCatalogEntry, PlatformRole } from '../api/types'
import { useAuthStore } from '../stores/auth'

function groupByModule(perms: PermissionCatalogEntry[]): Map<string, PermissionCatalogEntry[]> {
  const m = new Map<string, PermissionCatalogEntry[]>()
  for (const p of perms) {
    const k = p.module || 'other'
    const arr = m.get(k) ?? []
    arr.push(p)
    m.set(k, arr)
  }
  for (const arr of m.values()) {
    arr.sort((a, b) => a.code.localeCompare(b.code))
  }
  return new Map([...m.entries()].sort((a, b) => a[0].localeCompare(b[0])))
}

export default function RolesPage() {
  const hasPermission = useAuthStore((s) => s.hasPermission)
  const canManage = hasPermission('roles.manage')

  const catalogQ = usePermissionCatalog()
  const rolesQ = usePlatformRoles()
  const createM = useCreatePlatformRole()
  const updateM = useUpdatePlatformRole()
  const deleteM = useDeletePlatformRole()

  const grouped = useMemo(() => groupByModule(catalogQ.data ?? []), [catalogQ.data])

  const [createOpen, setCreateOpen] = useState(false)
  const [newCode, setNewCode] = useState('')
  const [newName, setNewName] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [newPerms, setNewPerms] = useState<Set<string>>(() => new Set())

  const [editRole, setEditRole] = useState<PlatformRole | null>(null)
  const [editName, setEditName] = useState('')
  const [editDesc, setEditDesc] = useState('')
  const [editPerms, setEditPerms] = useState<Set<string>>(() => new Set())

  function openEdit(r: PlatformRole) {
    setEditRole(r)
    setEditName(r.name)
    setEditDesc(r.description ?? '')
    setEditPerms(new Set(r.permissions.map((p) => p.code)))
  }

  function toggle(setter: React.Dispatch<React.SetStateAction<Set<string>>>, code: string) {
    setter((prev) => {
      const n = new Set(prev)
      if (n.has(code)) n.delete(code)
      else n.add(code)
      return n
    })
  }

  async function submitCreate() {
    try {
      await createM.mutateAsync({
        code: newCode.trim().toLowerCase(),
        name: newName.trim(),
        description: newDesc.trim() || null,
        permission_codes: [...newPerms],
      })
      toast.success('Rol creado')
      setCreateOpen(false)
      setNewCode('')
      setNewName('')
      setNewDesc('')
      setNewPerms(new Set())
    } catch {
      toast.error('No se pudo crear (código duplicado o inválido)')
    }
  }

  async function submitEdit() {
    if (!editRole) return
    if (editRole.is_system) {
      toast.error('Los roles de sistema no se editan desde aquí')
      return
    }
    try {
      await updateM.mutateAsync({
        roleId: editRole.id,
        name: editName.trim(),
        description: editDesc.trim() || null,
        permission_codes: [...editPerms],
      })
      toast.success('Rol actualizado')
      setEditRole(null)
    } catch {
      toast.error('No se pudo guardar')
    }
  }

  async function confirmDelete(r: PlatformRole) {
    if (r.is_system) {
      toast.error('No se eliminan roles de sistema')
      return
    }
    if (!window.confirm(`¿Eliminar el rol «${r.name}» (${r.code})?`)) return
    try {
      await deleteM.mutateAsync(r.id)
      toast.success('Rol eliminado')
    } catch {
      toast.error('No se pudo eliminar (¿usuarios asignados?)')
    }
  }

  const rows = rolesQ.data ?? []

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Roles y permisos</h1>
          <p className="text-slate-500 text-sm max-w-3xl">
            Los permisos controlan qué ve cada usuario en el panel. Para acceso solo a bandejas GYB sobre
            correos concretos, usá un rol con <code className="text-xs">mailbox.view_delegated</code> y en{' '}
            <strong>Usuarios</strong> → <em>Delegar buzones</em> marcá las cuentas permitidas.
          </p>
        </div>
        {canManage ? (
          <Button onClick={() => setCreateOpen(true)}>Nuevo rol</Button>
        ) : null}
      </div>

      <Card>
        {rolesQ.isLoading ? (
          <p className="text-slate-500">Cargando…</p>
        ) : rolesQ.isError ? (
          <p className="text-red-600">No se pudieron cargar los roles</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="text-left text-slate-500">
                <tr>
                  <th className="py-2 pr-2">Código</th>
                  <th className="pr-2">Nombre</th>
                  <th className="pr-2">Permisos</th>
                  <th className="pr-2">Tipo</th>
                  <th className="text-right">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-t border-slate-100 dark:border-slate-800">
                    <td className="py-2 font-mono text-xs">{r.code}</td>
                    <td>{r.name}</td>
                    <td className="text-xs text-slate-600 dark:text-slate-400 max-w-md">
                      {r.permissions.length === 0 ? '—' : `${r.permissions.length} permisos`}
                    </td>
                    <td>
                      {r.is_system ? (
                        <Badge color="gray">sistema</Badge>
                      ) : (
                        <Badge color="info">personalizado</Badge>
                      )}
                    </td>
                    <td className="text-right space-x-1 whitespace-nowrap">
                      <Button size="xs" color="light" onClick={() => openEdit(r)}>
                        Ver / editar
                      </Button>
                      {canManage && !r.is_system ? (
                        <Button size="xs" color="failure" onClick={() => void confirmDelete(r)}>
                          Eliminar
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

      <Modal show={createOpen} onClose={() => setCreateOpen(false)} size="xl">
        <Modal.Header>Nuevo rol personalizado</Modal.Header>
        <Modal.Body className="space-y-3 max-h-[80vh] overflow-y-auto">
          <div>
            <Label value="Código (slug, en minúsculas)" />
            <TextInput
              value={newCode}
              onChange={(e) => setNewCode(e.target.value)}
              placeholder="ej: auditor_cliente_a"
            />
          </div>
          <div>
            <Label value="Nombre visible" />
            <TextInput value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="Nombre" />
          </div>
          <div>
            <Label value="Descripción (opcional)" />
            <TextInput value={newDesc} onChange={(e) => setNewDesc(e.target.value)} />
          </div>
          <p className="text-xs text-slate-500">Marcá los permisos que tendrán los usuarios con este rol.</p>
          {catalogQ.isLoading ? (
            <p className="text-sm text-slate-500">Cargando catálogo…</p>
          ) : (
            [...grouped.entries()].map(([mod, perms]) => (
              <div key={mod} className="border border-slate-200 dark:border-slate-700 rounded-lg p-2">
                <div className="text-xs font-semibold text-slate-600 dark:text-slate-300 mb-2 uppercase">
                  {mod}
                </div>
                <div className="grid gap-1 sm:grid-cols-2">
                  {perms.map((p) => (
                    <label key={p.code} className="flex items-start gap-2 text-xs cursor-pointer">
                      <Checkbox checked={newPerms.has(p.code)} onChange={() => toggle(setNewPerms, p.code)} />
                      <span>
                        <span className="font-mono">{p.code}</span>
                        {p.description ? (
                          <span className="block text-slate-500">{p.description}</span>
                        ) : null}
                      </span>
                    </label>
                  ))}
                </div>
              </div>
            ))
          )}
        </Modal.Body>
        <Modal.Footer>
          <Button color="gray" onClick={() => setCreateOpen(false)}>
            Cancelar
          </Button>
          <Button onClick={() => void submitCreate()} disabled={createM.isPending}>
            Crear
          </Button>
        </Modal.Footer>
      </Modal>

      <Modal show={!!editRole} onClose={() => setEditRole(null)} size="xl">
        <Modal.Header>{editRole ? `Rol: ${editRole.code}` : ''}</Modal.Header>
        <Modal.Body className="space-y-3 max-h-[80vh] overflow-y-auto">
          {editRole?.is_system ? (
            <p className="text-sm text-amber-800 dark:text-amber-200">
              Rol de sistema: los permisos se gestionan desde migraciones / base de datos. Solo podés revisar
              la lista.
            </p>
          ) : null}
          <div>
            <Label value="Nombre" />
            <TextInput
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              disabled={!!editRole?.is_system}
            />
          </div>
          <div>
            <Label value="Descripción" />
            <TextInput value={editDesc} onChange={(e) => setEditDesc(e.target.value)} disabled={!!editRole?.is_system} />
          </div>
          {catalogQ.isLoading || !editRole ? null : (
            [...grouped.entries()].map(([mod, perms]) => (
              <div key={mod} className="border border-slate-200 dark:border-slate-700 rounded-lg p-2">
                <div className="text-xs font-semibold text-slate-600 dark:text-slate-300 mb-2 uppercase">
                  {mod}
                </div>
                <div className="grid gap-1 sm:grid-cols-2">
                  {perms.map((p) => (
                    <label key={p.code} className="flex items-start gap-2 text-xs cursor-pointer">
                      <Checkbox
                        checked={editPerms.has(p.code)}
                        disabled={!!editRole.is_system}
                        onChange={() => toggle(setEditPerms, p.code)}
                      />
                      <span>
                        <span className="font-mono">{p.code}</span>
                        {p.description ? (
                          <span className="block text-slate-500">{p.description}</span>
                        ) : null}
                      </span>
                    </label>
                  ))}
                </div>
              </div>
            ))
          )}
        </Modal.Body>
        <Modal.Footer>
          <Button color="gray" onClick={() => setEditRole(null)}>
            Cerrar
          </Button>
          {editRole && !editRole.is_system && canManage ? (
            <Button onClick={() => void submitEdit()} disabled={updateM.isPending}>
              Guardar
            </Button>
          ) : null}
        </Modal.Footer>
      </Modal>
    </div>
  )
}
