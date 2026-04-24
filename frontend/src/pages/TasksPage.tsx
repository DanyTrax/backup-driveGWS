import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Badge, Button, Card, Checkbox, Label, Modal, Select, TextInput, Textarea } from 'flowbite-react'
import { HiPencil, HiPlay, HiPlus } from 'react-icons/hi'
import toast from 'react-hot-toast'
import api from '../api/client'
import {
  useAccounts,
  useCreateTask,
  useRunTask,
  useTasks,
  useUpdateTask,
  type TaskPayload,
} from '../api/hooks'
import type { BackupTask, WorkspaceAccount } from '../api/types'

function formatApiDetail(d: unknown): string | null {
  if (d == null) return null
  if (typeof d === 'string') return d
  if (Array.isArray(d)) {
    return d
      .map((item) => {
        if (item && typeof item === 'object' && 'msg' in item)
          return String((item as { msg: string }).msg)
        return JSON.stringify(item)
      })
      .join(' · ')
  }
  if (typeof d === 'object') return JSON.stringify(d)
  return String(d)
}

function toastTaskSaveError(err: unknown) {
  const ax = err as { response?: { status?: number; data?: { detail?: unknown } }; message?: string }
  const st = ax.response?.status
  const d = ax.response?.data?.detail
  if (st === 403) {
    toast.error('No tenés permiso para crear o editar tareas.')
    return
  }
  if (
    typeof d === 'object' &&
    d !== null &&
    (d as { error?: string }).error === 'task_create_failed'
  ) {
    const reason = (d as { reason?: string }).reason ?? ''
    toast.error(
      reason
        ? `Error al crear la tarea: ${reason.slice(0, 380)}`
        : 'Error al crear la tarea. Revisá docker logs msa-backup-app.',
    )
    return
  }
  if (
    typeof d === 'object' &&
    d !== null &&
    (d as { error?: string }).error === 'accounts_backup_not_enabled'
  ) {
    const emails = (d as { emails?: string[] }).emails ?? []
    toast.error(
      emails.length
        ? `El servidor indica que estas cuentas no tienen backup activo: ${emails.join(', ')}. En Cuentas verificá «activo», sincronizá directorio o recargá la página.`
        : 'Hay cuentas sin backup activo en la tarea.',
    )
    return
  }
  if (d === 'unknown_account_ids') {
    toast.error('ID de cuenta inválido o duplicado. Recargá la página y volvé a marcar las cuentas.')
    return
  }
  if (d === 'invalid_account_id') {
    toast.error('Formato de ID de cuenta inválido. Recargá la página.')
    return
  }
  if (st === 422) {
    const msg = formatApiDetail(d)
    toast.error(
      msg
        ? `Revisá el formulario: ${msg.slice(0, 400)}`
        : 'Datos de la tarea inválidos. Revisá hora, modo y campos obligatorios.',
    )
    return
  }
  const detailMsg = formatApiDetail(d)
  if (detailMsg && st && st >= 400) {
    toast.error(`No se pudo guardar la tarea: ${detailMsg.slice(0, 420)}`)
    return
  }
  if (!ax.response) {
    toast.error(
      ax.message?.includes('Network')
        ? 'Sin conexión con el servidor. Revisá red o VPN.'
        : 'Sin respuesta del servidor (timeout o corte). Reintentá.',
    )
    return
  }
  toast.error(
    'No se pudo guardar la tarea. Revisá docker logs msa-backup-app y la consola de red (F12).',
  )
}

function emptyPayload(): TaskPayload {
  return {
    name: '',
    description: '',
    is_enabled: true,
    scope: 'gmail',
    mode: 'incremental',
    schedule_kind: 'daily',
    cron_expression: null,
    run_at_hour: 3,
    run_at_minute: 0,
    timezone: 'America/Bogota',
    retention_policy: { keep_drive_snapshots: 0 },
    filters: {},
    notify_channels: {},
    dry_run: false,
    checksum_enabled: true,
    max_parallel_accounts: 2,
    account_ids: [],
  }
}

export default function TasksPage() {
  const qc = useQueryClient()
  const { data: tasks = [], isLoading } = useTasks()
  const { data: enabledAccounts = [] } = useAccounts(true)
  const run = useRunTask()
  const create = useCreateTask()
  const update = useUpdateTask()

  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<BackupTask | null>(null)
  const [form, setForm] = useState<TaskPayload>(emptyPayload)
  const [datedRun, setDatedRun] = useState(false)
  const [runAfterSave, setRunAfterSave] = useState(false)

  useEffect(() => {
    if (!modalOpen) return
    if (editing) {
      const f = editing.filters as Record<string, unknown> | undefined
      setForm({
        name: editing.name,
        description: editing.description,
        is_enabled: editing.is_enabled,
        scope: editing.scope,
        mode: editing.mode,
        schedule_kind: editing.schedule_kind,
        cron_expression: editing.cron_expression,
        run_at_hour: editing.run_at_hour,
        run_at_minute: editing.run_at_minute,
        timezone: editing.timezone,
        retention_policy: { ...editing.retention_policy },
        filters: { ...editing.filters },
        notify_channels: { ...editing.notify_channels },
        dry_run: editing.dry_run,
        checksum_enabled: editing.checksum_enabled,
        max_parallel_accounts: editing.max_parallel_accounts,
        account_ids: [...editing.account_ids],
      })
      setDatedRun(f?.drive_layout === 'dated_run')
    } else {
      setForm(emptyPayload())
      setDatedRun(false)
    }
  }, [editing, modalOpen])

  function openCreate() {
    setEditing(null)
    setRunAfterSave(false)
    setModalOpen(true)
  }

  function openEdit(t: BackupTask) {
    setEditing(t)
    setRunAfterSave(false)
    setModalOpen(true)
  }

  function toggleAccount(id: string) {
    setForm((prev) => ({
      ...prev,
      account_ids: prev.account_ids.includes(id)
        ? prev.account_ids.filter((x) => x !== id)
        : [...prev.account_ids, id],
    }))
  }

  async function save() {
    const filters: Record<string, unknown> = { ...form.filters }
    if (datedRun && (form.scope === 'drive_root' || form.scope === 'drive_computadoras' || form.scope === 'full')) {
      filters.drive_layout = 'dated_run'
    } else {
      delete filters.drive_layout
    }

    let freshEnabled: WorkspaceAccount[] = enabledAccounts
    try {
      freshEnabled = await qc.fetchQuery({
        queryKey: ['accounts', true, 'preflight-save'],
        queryFn: async () =>
          (
            await api.get<WorkspaceAccount[]>('/accounts', {
              params: { enabled: true, _t: Date.now() },
            })
          ).data,
        staleTime: 0,
      })
    } catch {
      toast.error('No se pudo actualizar la lista de cuentas. Reintentá.')
      return
    }

    const allowed = new Set(freshEnabled.map((a) => a.id))
    const account_ids = form.account_ids.filter((id) => allowed.has(id))
    if (form.account_ids.length > 0 && account_ids.length === 0) {
      toast.error(
        'Ninguna cuenta seleccionada sigue con backup activo. Abrí Cuentas, verificá «activo» y recargá esta pantalla.',
      )
      return
    }
    if (account_ids.length < form.account_ids.length) {
      toast(
        'Se quitaron de la tarea cuentas que ya no tienen backup activo (datos actualizados desde el servidor).',
        { icon: '⚠️' },
      )
    }

    const payload: TaskPayload = { ...form, filters, account_ids }

    try {
      let taskId: string
      if (editing) {
        await update.mutateAsync({ id: editing.id, payload })
        taskId = editing.id
        toast.success('Tarea actualizada')
      } else {
        const t = await create.mutateAsync(payload)
        taskId = t.id
        toast.success('Tarea creada')
      }
      setModalOpen(false)
      if (runAfterSave) {
        try {
          const r = await run.mutateAsync(taskId)
          toast.success(`${r.queued} jobs · lote ${r.batch_id.slice(0, 8)}…`)
        } catch {
          toast.error('Tarea guardada pero no se pudo ejecutar ahora')
        }
      }
    } catch (err) {
      toastTaskSaveError(err)
    }
  }

  const driveScope = form.scope === 'drive_root' || form.scope === 'drive_computadoras' || form.scope === 'full'

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Tareas de backup</h1>
          <p className="text-slate-500">
            Definí Gmail y Drive por separado; asigná solo cuentas con backup activo. La programación
            automática por minuto aplica hoy a tareas <strong>diarias</strong> (beat interno).
          </p>
        </div>
        <Button onClick={openCreate}>
          <HiPlus className="h-5 w-5 mr-2" /> Nueva tarea
        </Button>
      </div>

      <Card>
        {isLoading ? (
          <p className="text-slate-500">Cargando…</p>
        ) : tasks.length === 0 ? (
          <p className="text-slate-500">
            No hay tareas. Usá <strong>Nueva tarea</strong> para crear una (Gmail o Drive) y asigná
            cuentas.
          </p>
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
                    <td className="text-right space-x-2">
                      <Button size="xs" color="light" onClick={() => openEdit(t)}>
                        <HiPencil className="h-4 w-4 mr-1" /> Editar
                      </Button>
                      <Button
                        size="xs"
                        onClick={() =>
                          run.mutate(t.id, {
                            onSuccess: (data) =>
                              toast.success(
                                `${data.queued} jobs en cola · lote ${data.batch_id.slice(0, 8)}…`,
                              ),
                            onError: () =>
                              toast.error('No se pudo encolar (¿sin cuentas con backup activo?)'),
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

      <Modal show={modalOpen} onClose={() => setModalOpen(false)} size="xl">
        <Modal.Header>{editing ? 'Editar tarea' : 'Nueva tarea'}</Modal.Header>
        <Modal.Body className="space-y-4 max-h-[70vh] overflow-y-auto">
          <div>
            <Label htmlFor="t-name" value="Nombre" />
            <TextInput
              id="t-name"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              required
            />
          </div>
          <div>
            <Label htmlFor="t-desc" value="Descripción" />
            <Textarea
              id="t-desc"
              rows={2}
              value={form.description ?? ''}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <Label value="Alcance" />
              <Select
                value={form.scope}
                onChange={(e) => setForm((f) => ({ ...f, scope: e.target.value }))}
              >
                <option value="gmail">Solo Gmail</option>
                <option value="drive_root">Drive — raíz</option>
                <option value="drive_computadoras">Drive — carpeta Computadoras</option>
                <option value="full">Gmail + Drive (raíz)</option>
              </Select>
            </div>
            <div>
              <Label value="Modo" />
              <Select
                value={form.mode}
                onChange={(e) => setForm((f) => ({ ...f, mode: e.target.value }))}
              >
                <option value="incremental">Incremental (copy; actualiza en un solo árbol)</option>
                <option value="full">Completo (copy)</option>
                <option value="mirror">Espejo (sync; borra en destino si falta en origen)</option>
              </Select>
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <Label value="Programación" />
              <Select
                value={form.schedule_kind}
                onChange={(e) => setForm((f) => ({ ...f, schedule_kind: e.target.value }))}
              >
                <option value="daily">Diaria (auto a la hora indicada)</option>
                <option value="manual">Manual</option>
                <option value="weekly">Semanal (requiere cron; auto pendiente)</option>
                <option value="custom_cron">Cron personalizado</option>
              </Select>
            </div>
            <div>
              <Label htmlFor="t-h" value="Hora (0–23)" />
              <TextInput
                id="t-h"
                type="number"
                min={0}
                max={23}
                value={form.run_at_hour ?? 0}
                onChange={(e) =>
                  setForm((f) => ({ ...f, run_at_hour: parseInt(e.target.value, 10) || 0 }))
                }
              />
            </div>
            <div>
              <Label htmlFor="t-m" value="Minuto (0–59)" />
              <TextInput
                id="t-m"
                type="number"
                min={0}
                max={59}
                value={form.run_at_minute ?? 0}
                onChange={(e) =>
                  setForm((f) => ({ ...f, run_at_minute: parseInt(e.target.value, 10) || 0 }))
                }
              />
            </div>
          </div>
          {form.schedule_kind === 'custom_cron' && (
            <div>
              <Label htmlFor="t-cron" value="Expresión cron" />
              <TextInput
                id="t-cron"
                value={form.cron_expression ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, cron_expression: e.target.value || null }))}
                placeholder="0 3 * * *"
              />
            </div>
          )}
          {driveScope && (
            <div className="flex items-center gap-2">
              <Checkbox
                id="dated"
                checked={datedRun}
                onChange={(e) => setDatedRun(e.target.checked)}
              />
              <Label htmlFor="dated" value="Vault: subcarpeta por ejecución (MSA_Runs/AAAA-MM-DDTHH-MM/)" />
            </div>
          )}
          {datedRun && driveScope && (
            <div>
              <Label
                htmlFor="t-keep-snaps"
                value="Retención Drive: mantener últimas N corridas bajo MSA_Runs (0 = no borrar automático)"
              />
              <TextInput
                id="t-keep-snaps"
                type="number"
                min={0}
                max={500}
                value={Number(
                  (form.retention_policy as Record<string, unknown>).keep_drive_snapshots ?? 0,
                )}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    retention_policy: {
                      ...f.retention_policy,
                      keep_drive_snapshots: Math.max(0, parseInt(e.target.value, 10) || 0),
                    },
                  }))
                }
              />
              <p className="text-xs text-slate-500 mt-1">
                Gmail/Maildir no usa este límite. Al cambiar N, la poda corre en la próxima ejecución
                exitosa de backup Drive de esta tarea.
              </p>
            </div>
          )}
          <p className="text-xs text-slate-500">
            Modo incremental en un solo árbol: dejá desmarcado lo anterior. La opción fechada guarda
            cada corrida bajo una carpeta nueva en el vault (árbol completo de esa ejecución). Delta
            archivo-a-archivo vs la corrida anterior se puede añadir después con compare-dest en
            rclone.
          </p>
          <div>
            <Label value="Cuentas (solo con backup activo)" />
            <div className="mt-2 max-h-40 overflow-y-auto border border-slate-200 dark:border-slate-700 rounded-lg p-2 space-y-1">
              {enabledAccounts.length === 0 ? (
                <p className="text-sm text-slate-500">No hay cuentas aprobadas. Activá backup en Cuentas.</p>
              ) : (
                enabledAccounts.map((a) => (
                  <label key={a.id} className="flex items-center gap-2 text-sm cursor-pointer">
                    <Checkbox
                      checked={form.account_ids.includes(a.id)}
                      onChange={() => toggleAccount(a.id)}
                    />
                    <span>{a.email}</span>
                  </label>
                ))
              )}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label htmlFor="t-par" value="Cuentas en paralelo" />
              <TextInput
                id="t-par"
                type="number"
                min={1}
                max={32}
                value={form.max_parallel_accounts}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    max_parallel_accounts: parseInt(e.target.value, 10) || 1,
                  }))
                }
              />
            </div>
            <div className="flex items-end gap-4 pb-2">
              <label className="flex items-center gap-2 text-sm">
                <Checkbox
                  checked={form.dry_run}
                  onChange={(e) => setForm((f) => ({ ...f, dry_run: e.target.checked }))}
                />
                Dry-run
              </label>
              <label className="flex items-center gap-2 text-sm">
                <Checkbox
                  checked={form.is_enabled}
                  onChange={(e) => setForm((f) => ({ ...f, is_enabled: e.target.checked }))}
                />
                Tarea habilitada
              </label>
            </div>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <Checkbox checked={runAfterSave} onChange={(e) => setRunAfterSave(e.target.checked)} />
            Ejecutar en cuanto guardar (prueba)
          </label>
        </Modal.Body>
        <Modal.Footer>
          <Button onClick={save} disabled={!form.name.trim() || create.isPending || update.isPending}>
            Guardar
          </Button>
          <Button color="gray" onClick={() => setModalOpen(false)}>
            Cancelar
          </Button>
        </Modal.Footer>
      </Modal>
    </div>
  )
}
