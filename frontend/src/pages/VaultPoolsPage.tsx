import { useState } from 'react'
import { Badge, Button, Card, Label, Modal, TextInput, Textarea } from 'flowbite-react'
import toast from 'react-hot-toast'
import {
  useCreateVaultPool,
  useDeleteVaultPool,
  useProvisionVaultPool,
  useUpdateVaultPool,
  useVaultPools,
} from '../api/hooks'
import type { VaultPool } from '../api/types'
import { useAuthStore } from '../stores/auth'

export default function VaultPoolsPage() {
  const canEdit = useAuthStore((s) => s.hasPermission('settings.edit'))
  const listQ = useVaultPools()
  const provisionM = useProvisionVaultPool()
  const createM = useCreateVaultPool()
  const updateM = useUpdateVaultPool()
  const deleteM = useDeleteVaultPool()

  const [provisionOpen, setProvisionOpen] = useState(false)
  const [manualOpen, setManualOpen] = useState(false)
  const [editRow, setEditRow] = useState<VaultPool | null>(null)
  const [name, setName] = useState('')
  const [sharedDriveId, setSharedDriveId] = useState('')
  const [rootFolderId, setRootFolderId] = useState('')
  const [rootFolderName, setRootFolderName] = useState('BackupRoot')
  const [driveDisplayName, setDriveDisplayName] = useState('')
  const [description, setDescription] = useState('')

  function resetForm() {
    setName('')
    setSharedDriveId('')
    setRootFolderId('')
    setRootFolderName('BackupRoot')
    setDriveDisplayName('')
    setDescription('')
  }

  function openProvision() {
    resetForm()
    setProvisionOpen(true)
  }

  function openManual() {
    resetForm()
    setManualOpen(true)
  }

  function openEdit(row: VaultPool) {
    setEditRow(row)
    setName(row.name)
    setSharedDriveId(row.shared_drive_id)
    setRootFolderId(row.root_folder_id)
    setDescription(row.description ?? '')
  }

  async function onProvision() {
    const nm = name.trim()
    if (!nm) {
      toast.error('Indicá un nombre para el pool.')
      return
    }
    try {
      const row = await provisionM.mutateAsync({
        name: nm,
        description: description.trim() || null,
        root_folder_name: rootFolderName.trim() || 'BackupRoot',
        drive_display_name: driveDisplayName.trim() || null,
      })
      toast.success(`Pool creado en Google: ${row.name}`)
      setProvisionOpen(false)
      resetForm()
    } catch (err: unknown) {
      const st = (err as { response?: { status?: number; data?: { detail?: unknown } } })?.response
        ?.status
      const detail = (err as { response?: { data?: { detail?: { message?: string } | string } } })
        ?.response?.data?.detail
      const msg =
        typeof detail === 'object' && detail && 'message' in detail
          ? String(detail.message)
          : typeof detail === 'string'
            ? detail
            : null
      if (st === 409) toast.error('Ya existe un pool con ese nombre en el panel.')
      else if (st === 502) toast.error(msg || 'Google rechazó crear la unidad compartida.')
      else toast.error(msg || 'No se pudo crear el pool automáticamente.')
    }
  }

  async function onManualCreate() {
    try {
      await createM.mutateAsync({
        name: name.trim(),
        shared_drive_id: sharedDriveId.trim(),
        root_folder_id: rootFolderId.trim(),
        description: description.trim() || null,
      })
      toast.success('Pool registrado.')
      setManualOpen(false)
      resetForm()
    } catch {
      toast.error('No se pudo registrar (revisá IDs y permisos SA).')
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
    if (!window.confirm(`¿Eliminar pool "${row.name}" del panel? (no borra la unidad en Google)`)) return
    try {
      await deleteM.mutateAsync(row.id)
      toast.success('Pool eliminado del panel.')
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
            La plataforma puede <strong>crear la unidad compartida en Google</strong>, dar acceso a la
            Service Account y preparar la carpeta raíz (por defecto <code className="text-xs">BackupRoot</code>
            ). Luego asigná cuentas en <strong>Cuentas → Asignar</strong>.
          </p>
        </div>
        {canEdit ? (
          <div className="flex flex-wrap gap-2">
            <Button onClick={openProvision}>Crear pool en Google</Button>
            <Button color="gray" onClick={openManual}>
              Registrar pool existente
            </Button>
          </div>
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
                {(listQ.data ?? []).length === 0 ? (
                  <tr>
                    <td colSpan={canEdit ? 5 : 4} className="py-8 text-center text-slate-500">
                      Sin pools. Usá «Crear pool en Google» para el primer vault adicional.
                    </td>
                  </tr>
                ) : (
                  (listQ.data ?? []).map((row) => (
                    <tr key={row.id} className="border-b border-slate-100 dark:border-slate-800">
                      <td className="py-2 pr-3 font-medium">{row.name}</td>
                      <td className="py-2 pr-3 font-mono text-xs break-all">{row.shared_drive_id}</td>
                      <td className="py-2 pr-3 font-mono text-xs break-all">{row.root_folder_id}</td>
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
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Modal show={provisionOpen} onClose={() => setProvisionOpen(false)} size="lg">
        <Modal.Header>Crear pool en Google (automático)</Modal.Header>
        <Modal.Body className="space-y-3 text-sm">
          <p className="text-slate-500 dark:text-slate-400">
            Se creará una unidad compartida, la Service Account quedará como Manager y la carpeta raíz
            para las cuentas que asignes a este pool.
          </p>
          <div>
            <Label value="Nombre del pool (panel)" />
            <TextInput
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Vault 02 — cuentas pesadas"
            />
          </div>
          <div>
            <Label value="Nombre en Google Drive (opcional)" />
            <TextInput
              value={driveDisplayName}
              onChange={(e) => setDriveDisplayName(e.target.value)}
              placeholder="MSA Backup — Vault 02"
            />
          </div>
          <div>
            <Label value="Carpeta raíz dentro del pool" />
            <TextInput
              value={rootFolderName}
              onChange={(e) => setRootFolderName(e.target.value)}
              placeholder="BackupRoot"
            />
          </div>
          <div>
            <Label value="Descripción (opcional)" />
            <Textarea rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>
        </Modal.Body>
        <Modal.Footer>
          <Button onClick={() => void onProvision()} disabled={provisionM.isPending}>
            Crear en Google
          </Button>
          <Button color="gray" onClick={() => setProvisionOpen(false)}>
            Cancelar
          </Button>
        </Modal.Footer>
      </Modal>

      <Modal show={manualOpen} onClose={() => setManualOpen(false)} size="lg">
        <Modal.Header>Registrar pool existente</Modal.Header>
        <Modal.Body className="space-y-3">
          <p className="text-sm text-slate-500">
            Solo si ya creaste la unidad compartida a mano en Google Drive.
          </p>
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
          <Button onClick={() => void onManualCreate()} disabled={createM.isPending}>
            Registrar
          </Button>
          <Button color="gray" onClick={() => setManualOpen(false)}>
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
        <TextInput value={props.name} onChange={(e) => props.setName(e.target.value)} />
      </div>
      <div>
        <Label value="Shared Drive ID" />
        <TextInput value={props.sharedDriveId} onChange={(e) => props.setSharedDriveId(e.target.value)} />
      </div>
      <div>
        <Label value="Carpeta raíz (ID)" />
        <TextInput value={props.rootFolderId} onChange={(e) => props.setRootFolderId(e.target.value)} />
      </div>
      <div>
        <Label value="Descripción (opcional)" />
        <Textarea rows={2} value={props.description} onChange={(e) => props.setDescription(e.target.value)} />
      </div>
    </>
  )
}
