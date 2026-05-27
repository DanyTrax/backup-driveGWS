import { useState } from 'react'
import { Badge, Button, Card, Label, Modal, TextInput, Textarea } from 'flowbite-react'
import toast from 'react-hot-toast'
import {
  useCreateVaultPool,
  useDeleteVaultPool,
  useUpdateVaultPool,
  useVaultPools,
} from '../api/hooks'
import type { VaultPool } from '../api/types'
import { useAuthStore } from '../stores/auth'

export default function VaultPoolsPage() {
  const canEdit = useAuthStore((s) => s.hasPermission('settings.edit'))
  const listQ = useVaultPools()
  const createM = useCreateVaultPool()
  const updateM = useUpdateVaultPool()
  const deleteM = useDeleteVaultPool()

  const [createOpen, setCreateOpen] = useState(false)
  const [editRow, setEditRow] = useState<VaultPool | null>(null)
  const [name, setName] = useState('')
  const [sharedDriveId, setSharedDriveId] = useState('')
  const [rootFolderId, setRootFolderId] = useState('')
  const [description, setDescription] = useState('')

  function resetForm() {
    setName('')
    setSharedDriveId('')
    setRootFolderId('')
    setDescription('')
  }

  function openCreate() {
    resetForm()
    setCreateOpen(true)
  }

  function openEdit(row: VaultPool) {
    setEditRow(row)
    setName(row.name)
    setSharedDriveId(row.shared_drive_id)
    setRootFolderId(row.root_folder_id)
    setDescription(row.description ?? '')
  }

  async function onCreate() {
    try {
      await createM.mutateAsync({
        name: name.trim(),
        shared_drive_id: sharedDriveId.trim(),
        root_folder_id: rootFolderId.trim(),
        description: description.trim() || null,
      })
      toast.success('Pool creado.')
      setCreateOpen(false)
      resetForm()
    } catch {
      toast.error('No se pudo crear el pool (revisá IDs y permisos SA).')
    }
  }

  async function onSaveEdit() {
    if (!editRow) return
    try {
      await updateM.mutateAsync({
        id: editRow.id,
        body: {
          name: name.trim(),
          shared_drive_id: sharedDriveId.trim(),
          root_folder_id: rootFolderId.trim(),
          description: description.trim() || null,
        },
      })
      toast.success('Pool actualizado.')
      setEditRow(null)
    } catch {
      toast.error('No se pudo actualizar.')
    }
  }

  async function onDelete(row: VaultPool) {
    if (row.account_count > 0) {
      toast.error('Hay cuentas asignadas a este pool.')
      return
    }
    if (!window.confirm(`¿Eliminar pool "${row.name}"?`)) return
    try {
      await deleteM.mutateAsync(row.id)
      toast.success('Pool eliminado.')
    } catch {
      toast.error('No se pudo eliminar.')
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Pools de bóveda</h1>
          <p className="text-slate-500 text-sm max-w-3xl mt-1">
            Unidades compartidas adicionales para repartir cuentas y evitar el límite de 400k ítems.
            Creá la Shared Drive en Google, agregá la SA como Manager y registrá aquí el ID de la unidad
            y la carpeta raíz (ej. BackupRoot).
          </p>
        </div>
        {canEdit ? (
          <Button onClick={openCreate}>Nuevo pool</Button>
        ) : null}
      </div>

      <Card>
        {listQ.isLoading ? (
          <p className="text-slate-500">Cargando…</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="text-left text-slate-500 border-b border-slate-200 dark:border-slate-700">
                <tr>
                  <th className="py-2 pr-3">Nombre</th>
                  <th className="py-2 pr-3">Shared Drive ID</th>
                  <th className="py-2 pr-3">Carpeta raíz</th>
                  <th className="py-2 pr-3">Cuentas</th>
                  {canEdit ? <th className="py-2 text-right">Acción</th> : null}
                </tr>
              </thead>
              <tbody>
                {(listQ.data ?? []).map((row) => (
                  <tr key={row.id} className="border-b border-slate-100 dark:border-slate-800">
                    <td className="py-2 pr-3 font-medium">{row.name}</td>
                    <td className="py-2 pr-3 font-mono text-xs">{row.shared_drive_id}</td>
                    <td className="py-2 pr-3 font-mono text-xs">{row.root_folder_id}</td>
                    <td className="py-2 pr-3">
                      <Badge color={row.account_count > 0 ? 'info' : 'gray'}>{row.account_count}</Badge>
                    </td>
                    {canEdit ? (
                      <td className="py-2 text-right space-x-2">
                        <Button size="xs" color="gray" onClick={() => openEdit(row)}>
                          Editar
                        </Button>
                        <Button size="xs" color="failure" onClick={() => void onDelete(row)}>
                          Eliminar
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

      <Modal show={createOpen} onClose={() => setCreateOpen(false)} size="lg">
        <Modal.Header>Nuevo pool de bóveda</Modal.Header>
        <Modal.Body className="space-y-3">
          <FormFields
            name={name}
            setName={setName}
            sharedDriveId={sharedDriveId}
            setSharedDriveId={setSharedDriveId}
            rootFolderId={rootFolderId}
            setRootFolderId={setRootFolderId}
            description={description}
            setDescription={setDescription}
          />
        </Modal.Body>
        <Modal.Footer>
          <Button onClick={() => void onCreate()} disabled={createM.isPending}>
            Crear
          </Button>
          <Button color="gray" onClick={() => setCreateOpen(false)}>
            Cancelar
          </Button>
        </Modal.Footer>
      </Modal>

      <Modal show={Boolean(editRow)} onClose={() => setEditRow(null)} size="lg">
        <Modal.Header>Editar pool</Modal.Header>
        <Modal.Body className="space-y-3">
          <FormFields
            name={name}
            setName={setName}
            sharedDriveId={sharedDriveId}
            setSharedDriveId={setSharedDriveId}
            rootFolderId={rootFolderId}
            setRootFolderId={setRootFolderId}
            description={description}
            setDescription={setDescription}
          />
        </Modal.Body>
        <Modal.Footer>
          <Button onClick={() => void onSaveEdit()} disabled={updateM.isPending}>
            Guardar
          </Button>
          <Button color="gray" onClick={() => setEditRow(null)}>
            Cancelar
          </Button>
        </Modal.Footer>
      </Modal>
    </div>
  )
}

function FormFields(props: {
  name: string
  setName: (v: string) => void
  sharedDriveId: string
  setSharedDriveId: (v: string) => void
  rootFolderId: string
  setRootFolderId: (v: string) => void
  description: string
  setDescription: (v: string) => void
}) {
  return (
    <>
      <div>
        <Label value="Nombre" />
        <TextInput value={props.name} onChange={(e) => props.setName(e.target.value)} placeholder="MSA Vault 02" />
      </div>
      <div>
        <Label value="Shared Drive ID" />
        <TextInput
          value={props.sharedDriveId}
          onChange={(e) => props.setSharedDriveId(e.target.value)}
          placeholder="0A…"
        />
      </div>
      <div>
        <Label value="Carpeta raíz (ID)" />
        <TextInput
          value={props.rootFolderId}
          onChange={(e) => props.setRootFolderId(e.target.value)}
          placeholder="ID de BackupRoot dentro del pool"
        />
      </div>
      <div>
        <Label value="Descripción (opcional)" />
        <Textarea rows={2} value={props.description} onChange={(e) => props.setDescription(e.target.value)} />
      </div>
    </>
  )
}
