import { Fragment, useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { AxiosError } from 'axios'
import { Badge, Button, Card, Checkbox, Label, Modal, Select, TextInput, Textarea } from 'flowbite-react'
import { HiPencil, HiPlay, HiPlus, HiTrash } from 'react-icons/hi'
import toast from 'react-hot-toast'
import api from '../api/client'
import {
  useAccounts,
  useCreateTask,
  useDeleteTask,
  useRunTask,
  useTaskBackupWaveStatus,
  useTasks,
  useUpdateTask,
  type TaskPayload,
} from '../api/hooks'
import type { BackupTask, BackupWaveStatusOut, RunEstimateOut, WorkspaceAccount } from '../api/types'

function TaskWaveSummary({ taskId }: { taskId: string }) {
  const { data, isLoading, isError } = useTaskBackupWaveStatus(taskId)
  if (isLoading)
    return <span className="text-xs text-slate-400">Consultando estado del lote…</span>
  if (isError || !data)
    return <span className="text-xs text-amber-600">No se pudo cargar el estado del lote.</span>
  return <TaskWaveSummaryBody data={data} />
}

function TaskWaveSummaryBody({ data }: { data: BackupWaveStatusOut }) {
  const busy = data.wave_in_progress || (data.active_jobs?.length ?? 0) > 0
  const aj = data.active_jobs ?? []
  if (!busy) {
    return (
      <div className="text-xs text-slate-500 dark:text-slate-400">
        Sin backups activos registrados en base de datos para esta tarea. Si acabás de encolar, el
        worker puede tardar unos segundos en crear el log.
      </div>
    )
  }
  return (
    <div className="text-xs space-y-2">
      <div className="font-medium text-slate-700 dark:text-slate-200">
        Lote en curso ({aj.length} job{aj.length === 1 ? '' : 's'} con estado running/queued/pending en
        BD)
      </div>
      <ul className="list-disc pl-4 space-y-1 text-slate-600 dark:text-slate-300">
        {aj.map((j) => (
          <li key={j.log_id}>
            <span className="font-mono">{j.email ?? j.account_id}</span> · {j.scope} ·{' '}
            <span className="uppercase">{j.status}</span>
            {j.started_at ? (
              <>
                {' '}
                · desde {j.started_at}
              </>
            ) : null}
            {' · '}
            <a
              className="text-blue-600 dark:text-blue-400 underline"
              href={`/logs?log=${encodeURIComponent(j.log_id)}`}
            >
              ver log
            </a>
          </li>
        ))}
      </ul>
      {data.idle_account_emails.length > 0 ? (
        <p className="text-slate-500 dark:text-slate-400">
          Cuentas sin job activo en BD todavía: {data.idle_account_emails.length} (p. ej. en cola de
          worker o pendientes cuando haya hueco).
        </p>
      ) : null}
      <p className="text-slate-500 dark:text-slate-400">
        Con empaquetado <strong>ZIP al vault</strong>, la compresión local y la subida rclone publican progreso en el
        detalle del log (Historial → fila → telemetría en vivo).
      </p>
      <p className="text-slate-400 dark:text-slate-500">{data.note}</p>
    </div>
  )
}

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
    const hint =
      typeof msg === 'string' &&
      (msg.includes('gmail_vault') ||
        msg.includes('vault_zip') ||
        msg.includes('overlap_days') ||
        msg.includes('vault_gmail_disable_push'))
        ? ' Revisá empaquetado vault Gmail (ZIP vs legacy) y que el alcance sea Gmail o Full.'
        : ''
    toast.error(
      msg
        ? `Revisá el formulario: ${msg.slice(0, 400)}${hint}`
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
  const remove = useDeleteTask()

  async function runTaskWithFeedback(taskId: string) {
    let estHint = ''
    try {
      const est: RunEstimateOut = (await api.get<RunEstimateOut>(`/tasks/${taskId}/run-estimate`)).data
      if (est.sum_minutes_min != null && est.sum_minutes_max != null) {
        estHint = ` · ~${est.sum_minutes_min}–${est.sum_minutes_max} min de trabajo aprox. (heurística, no fijo).`
      }
    } catch {
      /* sin estimado */
    }
    try {
      const data = await run.mutateAsync(taskId)
      const skipped = data.skipped_due_to_active?.length ?? 0
      let msg = `${data.queued} jobs en cola · lote ${data.batch_id.slice(0, 8)}…${estHint}`
      if (skipped > 0) {
        msg += ` · ${skipped} omitido(s) (backup ya en curso para esa cuenta)`
      }
      toast.success(msg)
    } catch (err) {
      const ax = err as AxiosError<{ detail?: unknown }>
      if (ax.response?.status === 409) {
        const d = ax.response.data?.detail
        const msg =
          d && typeof d === 'object' && d !== null && 'message' in d
            ? String((d as { message: string }).message)
            : 'Ya hay backups en curso para esta tarea y cuentas. Esperá o cancelá el lote activo.'
        toast.error(msg)
        return
      }
      toast.error('No se pudo encolar (¿sin cuentas con backup activo?)')
    }
  }
  const [modalOpen, setModalOpen] = useState(false)
  const [taskToDelete, setTaskToDelete] = useState<BackupTask | null>(null)
  const [editing, setEditing] = useState<BackupTask | null>(null)
  const [form, setForm] = useState<TaskPayload>(emptyPayload)
  const [datedRun, setDatedRun] = useState(false)
  const [driveIncrementalChain, setDriveIncrementalChain] = useState(false)
  const [gmailSkipMaildir, setGmailSkipMaildir] = useState(true)
  const [gmailVaultPackaging, setGmailVaultPackaging] = useState<
    'legacy_eml' | 'zip_only' | 'mixed'
  >('legacy_eml')
  const [vaultZipCadence, setVaultZipCadence] = useState<'weekly' | 'monthly' | 'none'>('weekly')
  const [vaultAnchorDow, setVaultAnchorDow] = useState(6)
  const [bootstrapUploadImmediate, setBootstrapUploadImmediate] = useState(true)
  const [overlapDays, setOverlapDays] = useState(1)
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
      setDriveIncrementalChain(f?.drive_dated_incremental_chain === true)
      setGmailSkipMaildir(f?.gmail_skip_maildir_import === true)
      const pkg = f?.gmail_vault_packaging
      setGmailVaultPackaging(
        pkg === 'zip_only' || pkg === 'mixed' || pkg === 'legacy_eml' ? pkg : 'legacy_eml',
      )
      const cad = f?.vault_zip_cadence
      setVaultZipCadence(
        cad === 'monthly' || cad === 'none' || cad === 'weekly' ? cad : 'weekly',
      )
      const ad = Number(f?.vault_anchor_dow)
      setVaultAnchorDow(Number.isFinite(ad) ? Math.min(6, Math.max(0, ad)) : 6)
      setBootstrapUploadImmediate(f?.bootstrap_upload_immediate !== false)
      const od = Number(f?.overlap_days)
      setOverlapDays(Number.isFinite(od) ? Math.min(366, Math.max(0, od)) : 1)
    } else {
      setForm(emptyPayload())
      setDatedRun(false)
      setDriveIncrementalChain(false)
      setGmailSkipMaildir(true)
      setGmailVaultPackaging('legacy_eml')
      setVaultZipCadence('weekly')
      setVaultAnchorDow(6)
      setBootstrapUploadImmediate(true)
      setOverlapDays(1)
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
    if (
      datedRun &&
      driveIncrementalChain &&
      (form.scope === 'drive_root' || form.scope === 'drive_computadoras' || form.scope === 'full')
    ) {
      filters.drive_dated_incremental_chain = true
    } else {
      delete filters.drive_dated_incremental_chain
    }

    if (form.scope === 'gmail' || form.scope === 'full') {
      filters.gmail_skip_maildir_import = gmailSkipMaildir
      filters.gmail_vault_packaging = gmailVaultPackaging
      if (gmailVaultPackaging === 'zip_only' || gmailVaultPackaging === 'mixed') {
        filters.vault_zip_cadence = vaultZipCadence
        filters.vault_anchor_dow = vaultAnchorDow
        filters.bootstrap_upload_immediate = bootstrapUploadImmediate
        filters.overlap_days = overlapDays
      } else {
        delete filters.vault_zip_cadence
        delete filters.vault_anchor_dow
        delete filters.bootstrap_upload_immediate
        delete filters.overlap_days
      }
    } else {
      delete filters.gmail_skip_maildir_import
      delete filters.gmail_vault_packaging
      delete filters.vault_zip_cadence
      delete filters.vault_anchor_dow
      delete filters.bootstrap_upload_immediate
      delete filters.overlap_days
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
        void runTaskWithFeedback(taskId)
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
            automática por minuto aplica hoy a tareas <strong>diarias</strong> (beat interno). Al
            pulsar <strong>Ejecutar</strong> se muestra un rango de minutos aproximado (heurística)
            antes de encolar.
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
                  <Fragment key={t.id}>
                    <tr className="border-t border-slate-100 dark:border-slate-800">
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
                      <td className="text-right space-x-2 whitespace-nowrap">
                        <Button size="xs" color="light" onClick={() => openEdit(t)}>
                          <HiPencil className="h-4 w-4 mr-1" /> Editar
                        </Button>
                        <Button
                          size="xs"
                          onClick={() => {
                            void runTaskWithFeedback(t.id)
                          }}
                        >
                          <HiPlay className="h-4 w-4 mr-1" /> Ejecutar
                        </Button>
                        <Button size="xs" color="failure" onClick={() => setTaskToDelete(t)}>
                          <HiTrash className="h-4 w-4 mr-1" /> Eliminar
                        </Button>
                      </td>
                    </tr>
                    <tr className="border-t border-slate-50 dark:border-slate-900">
                      <td colSpan={8} className="py-2 px-3 bg-slate-50/80 dark:bg-slate-900/40">
                        <TaskWaveSummary taskId={t.id} />
                      </td>
                    </tr>
                  </Fragment>
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
                <option value="drive_computadoras">
                  Drive — copias del PC (Computadoras / Computers, app de escritorio)
                </option>
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
          {form.scope === 'gmail' || form.scope === 'full' ? (
            <div className="space-y-4 border border-slate-200 dark:border-slate-600 rounded-lg p-3">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <Checkbox
                    id="gmail-skip-maildir"
                    checked={gmailSkipMaildir}
                    onChange={(e) => setGmailSkipMaildir(e.target.checked)}
                  />
                  <Label
                    htmlFor="gmail-skip-maildir"
                    value="Solo carpeta de trabajo GYB + vault (omitir Maildir)"
                  />
                </div>
                <p className="text-xs text-slate-500 pl-7">
                  Recomendado: un solo directorio local y la misma copia hacia 1-GMAIL en Drive. Desmarcá
                  si necesitás importar a Dovecot/IMAP en el servidor.
                </p>
              </div>
              <div>
                <Label value="Vault Gmail — empaquetado hacia 1-GMAIL" />
                <Select
                  value={gmailVaultPackaging}
                  onChange={(e) =>
                    setGmailVaultPackaging(e.target.value as 'legacy_eml' | 'zip_only' | 'mixed')
                  }
                  className="mt-1"
                >
                  <option value="legacy_eml">
                    Solo árbol .eml incremental (gyb_mbox), sin ZIP periódico
                  </option>
                  <option value="zip_only">Solo ZIP al vault (1-GMAIL/zips/…), sin copia eml</option>
                  <option value="mixed">ZIP periódico + copia eml (gyb_mbox)</option>
                </Select>
                <p className="text-xs text-slate-500 mt-1">
                  El ZIP reduce cantidad de ítems en Shared Drive. Requiere que el push al vault Gmail
                  esté habilitado (no uses «desactivar push vault» en filtros avanzados sin saberlo).
                </p>
              </div>
              {gmailVaultPackaging !== 'legacy_eml' ? (
                <div className="space-y-3 pl-0 md:pl-1 border-t border-slate-100 dark:border-slate-700 pt-3">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <Label value="Cadencia de sellado ZIP" />
                      <Select
                        value={vaultZipCadence}
                        onChange={(e) =>
                          setVaultZipCadence(e.target.value as 'weekly' | 'monthly' | 'none')
                        }
                      >
                        <option value="weekly">Semanal (día de anclaje)</option>
                        <option value="monthly">Mensual (día de anclaje)</option>
                        <option value="none">Solo bootstrap (un primer ZIP; sin recurrencia)</option>
                      </Select>
                    </div>
                    <div>
                      <Label value="Día de anclaje (subida ZIP)" />
                      <Select
                        value={String(vaultAnchorDow)}
                        onChange={(e) => setVaultAnchorDow(parseInt(e.target.value, 10) || 0)}
                      >
                        <option value="0">Lunes</option>
                        <option value="1">Martes</option>
                        <option value="2">Miércoles</option>
                        <option value="3">Jueves</option>
                        <option value="4">Viernes</option>
                        <option value="5">Sábado</option>
                        <option value="6">Domingo</option>
                      </Select>
                      <p className="text-xs text-slate-500 mt-1">
                        Convención Python (0=lunes … 6=domingo), en la zona horaria de la tarea.
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Checkbox
                      id="vault-bootstrap-immediate"
                      checked={bootstrapUploadImmediate}
                      onChange={(e) => setBootstrapUploadImmediate(e.target.checked)}
                    />
                    <Label
                      htmlFor="vault-bootstrap-immediate"
                      value="Primer ZIP sin sellado previo: subir en cuanto corra (no esperar día de anclaje)"
                    />
                  </div>
                  <div>
                    <Label htmlFor="vault-overlap" value="Solapamiento (días) en manifiesto ZIP" />
                    <TextInput
                      id="vault-overlap"
                      type="number"
                      min={0}
                      max={366}
                      value={overlapDays}
                      onChange={(e) =>
                        setOverlapDays(Math.min(366, Math.max(0, parseInt(e.target.value, 10) || 0)))
                      }
                    />
                    <p className="text-xs text-slate-500 mt-1">
                      Típico 1. Usado en metadatos del ZIP; la límite fina GYB/watermark es trabajo
                      aparte.
                    </p>
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}
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
                onChange={(e) => {
                  const on = e.target.checked
                  setDatedRun(on)
                  if (!on) setDriveIncrementalChain(false)
                }}
              />
              <Label htmlFor="dated" value="Vault: subcarpeta por ejecución (MSA_Runs/AAAA-MM-DDTHH-MM/)" />
            </div>
          )}
          {datedRun && driveScope && (
            <div className="flex items-center gap-2">
              <Checkbox
                id="drive-inc-chain"
                checked={driveIncrementalChain}
                onChange={(e) => setDriveIncrementalChain(e.target.checked)}
              />
              <Label
                htmlFor="drive-inc-chain"
                value="Cadena incremental (TOTAL + diario INC): solo sube cambios vs la corrida más reciente; nueva TOTAL si la retención borra la copia más antigua"
              />
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
            Sin «cadena incremental», cada carpeta fechada es una copia completa desde Drive. Con la
            cadena, rclone usa la corrida más reciente como referencia: las carpetas{' '}
            <code className="text-xs">(INC)</code> pueden contener solo ficheros nuevos o modificados
            respecto a esa referencia (restauración puede requerir combinar con copias anteriores).
            Poned <strong>retención N &gt; 0</strong> para podar copias viejas; cuando la poda quite
            una carpeta <code className="text-xs">(TOTAL)</code>, la siguiente corrida genera otra{' '}
            <code className="text-xs">(TOTAL)</code> (nuevo ancla). Si solo caen{' '}
            <code className="text-xs">(INC)</code>, siguen los incrementales diarios.
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
              <Label htmlFor="t-par" value="Cuentas Gmail en paralelo (lote / oleada)" />
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
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 max-w-md">
                Cuántos backups <strong>Gmail</strong> de esta tarea pueden ejecutarse a la vez. El resto espera en cola
                hasta que termine uno (incluye compresión ZIP y subida rclone al vault). No es lo mismo que{' '}
                <strong>solapamiento (días) en manifiesto ZIP</strong> (allí abajo, solo empaquetado vault). Tarea{' '}
                <strong>Full</strong>: Drive se encola para todas las cuentas en el primer pase; Gmail sigue este tope.
              </p>
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

      <Modal show={taskToDelete !== null} onClose={() => setTaskToDelete(null)} size="md">
        <Modal.Header>Eliminar tarea</Modal.Header>
        <Modal.Body>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            ¿Eliminar la tarea <strong>{taskToDelete?.name}</strong>? No borra backups ya hechos; solo
            la definición y la asignación de cuentas. El historial en Logs puede seguir mostrando
            ejecuciones antiguas ligadas a este ID.
          </p>
        </Modal.Body>
        <Modal.Footer>
          <Button
            color="failure"
            disabled={remove.isPending}
            onClick={() => {
              if (!taskToDelete) return
              const id = taskToDelete.id
              const name = taskToDelete.name
              remove.mutate(id, {
                onSuccess: () => {
                  toast.success(`Tarea «${name}» eliminada`)
                  setTaskToDelete(null)
                },
                onError: (err) => {
                  const st = (err as { response?: { status?: number } }).response?.status
                  if (st === 403) {
                    toast.error('No tenés permiso para eliminar tareas (se requiere tasks.delete).')
                  } else {
                    toast.error('No se pudo eliminar la tarea.')
                  }
                },
              })
            }}
          >
            Eliminar
          </Button>
          <Button color="gray" onClick={() => setTaskToDelete(null)}>
            Cancelar
          </Button>
        </Modal.Footer>
      </Modal>
    </div>
  )
}
