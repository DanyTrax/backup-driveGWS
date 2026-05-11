import { useMemo, useState } from 'react'
import { Badge, Button, Card, Label, Select, TextInput } from 'flowbite-react'
import { Link } from 'react-router-dom'
import { HiTrash, HiX } from 'react-icons/hi'
import toast from 'react-hot-toast'
import type { AxiosError } from 'axios'

import {
  useBulkDeleteRestoreJobs,
  useCancelRestoreJob,
  useDeleteGmailVaultMaterialize,
  useDeleteRestoreJob,
  useGmailVaultMaterializeRecent,
  useProfile,
  usePromoteGmailVaultMaterialize,
  useRestoreJobs,
} from '../api/hooks'
import type { GmailVaultMaterializeListItem, RestoreJob } from '../api/types'

function formatApiErr(err: unknown): string {
  const ax = err as AxiosError<{ detail?: unknown }>
  const d = ax.response?.data?.detail
  if (typeof d === 'string') return d
  if (d != null && typeof d === 'object' && 'error' in d && typeof (d as { error: string }).error === 'string')
    return (d as { error: string }).error
  if (d != null && typeof d === 'object') return JSON.stringify(d)
  return ax.message ?? 'Error'
}

function materializeZipProgressText(m: GmailVaultMaterializeListItem): string {
  const pj = m.progress_json
  const d = typeof pj.done_zips === 'number' ? pj.done_zips : null
  const p = typeof pj.planned_zips === 'number' ? pj.planned_zips : null
  if (d != null && p != null) return `${d}/${p}`
  if (p != null) return `0/${p}`
  return '—'
}

const RESTORE_STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: 'Todos los estados' },
  { value: 'pending', label: 'Pendiente' },
  { value: 'running', label: 'En ejecución' },
  { value: 'success', label: 'Éxito' },
  { value: 'failed', label: 'Fallido' },
  { value: 'cancelled', label: 'Cancelado' },
]

const RESTORE_SCOPE_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: 'Todos los alcances' },
  { value: 'drive_total', label: 'Drive total' },
  { value: 'drive_selective', label: 'Drive selectivo' },
  { value: 'gmail_mbox_bulk', label: 'Gmail mbox' },
  { value: 'gmail_message', label: 'Gmail mensaje' },
  { value: 'full_account', label: 'Cuenta completa' },
]

const MAT_STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: 'Todos' },
  { value: 'pending', label: 'Pendiente' },
  { value: 'downloading', label: 'Descargando' },
  { value: 'ready', label: 'Listo (ZIP en servidor)' },
  { value: 'promoted', label: 'En GYB trabajo' },
  { value: 'failed', label: 'Fallido' },
]

function scopeLabel(code: string): string {
  return RESTORE_SCOPE_OPTIONS.find((o) => o.value === code)?.label ?? code
}

function restoreBadgeColor(
  st: string,
): 'success' | 'failure' | 'info' | 'gray' | 'warning' {
  if (st === 'success') return 'success'
  if (st === 'failed') return 'failure'
  if (st === 'running') return 'info'
  if (st === 'pending') return 'warning'
  return 'gray'
}

export default function RestorePage() {
  const { data: profile } = useProfile()
  const perms = new Set(profile?.permissions ?? [])
  const canDeleteRestore = perms.has('restore.delete')
  const canCancelRestore = perms.has('restore.cancel')

  const [restoreStatus, setRestoreStatus] = useState('')
  const [restoreScope, setRestoreScope] = useState('')
  const [restoreSearch, setRestoreSearch] = useState('')

  const { data: restoreRaw = [], isLoading: restoreLoading } = useRestoreJobs({
    status_filter: restoreStatus || undefined,
    scope_filter: restoreScope || undefined,
    limit: 500,
  })

  const restoreRows = useMemo(() => {
    const q = restoreSearch.trim().toLowerCase()
    if (!q) return restoreRaw
    return restoreRaw.filter((j) => {
      const mail = (j.account_email ?? '').toLowerCase()
      const idp = j.target_account_id.toLowerCase()
      return mail.includes(q) || idp.includes(q)
    })
  }, [restoreRaw, restoreSearch])

  const cancelRestore = useCancelRestoreJob()
  const deleteRestore = useDeleteRestoreJob()
  const bulkDeleteRestore = useBulkDeleteRestoreJobs()

  const showVaultMat =
    Boolean(profile?.permissions?.includes('vault_drive.view_all')) ||
    Boolean(profile?.permissions?.includes('vault_drive.view_delegated'))
  const { data: matRecent = [], isLoading: matLoading } = useGmailVaultMaterializeRecent({
    enabled: showVaultMat,
  })
  const promoteMut = usePromoteGmailVaultMaterialize()
  const deleteMat = useDeleteGmailVaultMaterialize()

  const [matStatus, setMatStatus] = useState('')
  const [matSearch, setMatSearch] = useState('')

  const matRows = useMemo(() => {
    let rows = matRecent
    if (matStatus) rows = rows.filter((m) => m.status === matStatus)
    const q = matSearch.trim().toLowerCase()
    if (q)
      rows = rows.filter((m) => {
        const mail = (m.account_email ?? '').toLowerCase()
        return mail.includes(q) || m.account_id.toLowerCase().includes(q)
      })
    return rows
  }, [matRecent, matStatus, matSearch])

  const deletableRestoreCount = restoreRows.filter((j) => j.status !== 'running').length

  async function promoteRow(id: string) {
    try {
      await promoteMut.mutateAsync(id)
      toast.success('Datos fusionados en la carpeta GYB trabajo para esa cuenta.')
    } catch (err) {
      toast.error(formatApiErr(err).slice(0, 380))
    }
  }

  async function onCancelRestore(j: RestoreJob) {
    if (j.status !== 'pending' && j.status !== 'running') return
    try {
      await cancelRestore.mutateAsync(j.id)
      toast.success('Trabajo de restauración cancelado')
    } catch {
      toast.error('No se pudo cancelar')
    }
  }

  async function onDeleteRestore(j: RestoreJob) {
    if (j.status === 'running') {
      toast.error('Cancelá primero el trabajo en ejecución')
      return
    }
    if (!window.confirm(`¿Eliminar este registro de restauración (${j.id.slice(0, 8)}…)?`)) return
    try {
      await deleteRestore.mutateAsync(j.id)
      toast.success('Eliminado')
    } catch (err) {
      toast.error(formatApiErr(err).slice(0, 380))
    }
  }

  async function onBulkDeleteRestore() {
    const ids = restoreRows.filter((j) => j.status !== 'running').map((j) => j.id)
    if (!ids.length) {
      toast.error('No hay filas eliminables (en ejecución se omiten)')
      return
    }
    if (
      !window.confirm(`¿Eliminar ${ids.length} trabajo(s) de restauración visibles (no borra los «running»)?`)
    )
      return
    try {
      const r = await bulkDeleteRestore.mutateAsync(ids)
      if (r.deleted > 0) toast.success(`Eliminados: ${r.deleted}`)
      if (r.skipped_running.length) toast(`En ejecución omitidos: ${r.skipped_running.length}`, { icon: 'ℹ️' })
      if (r.not_found.length) toast(`IDs no encontrados: ${r.not_found.length}`, { icon: '⚠️' })
    } catch (err) {
      toast.error(formatApiErr(err).slice(0, 380))
    }
  }

  async function onDeleteMat(m: GmailVaultMaterializeListItem) {
    if (!window.confirm('¿Eliminar esta sesión de materialización y sus datos locales en el servidor?')) return
    try {
      await deleteMat.mutateAsync(m.id)
      toast.success('Sesión eliminada')
    } catch (err) {
      toast.error(formatApiErr(err).slice(0, 380))
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Trabajos de restauración</h1>
        <p className="text-slate-500">Drive total, selectivo y Gmail granular</p>
      </div>
      <Card>
        <div className="flex flex-col gap-4 mb-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 items-end">
            <div>
              <Label value="Estado" className="mb-1" />
              <Select value={restoreStatus} onChange={(e) => setRestoreStatus(e.target.value)}>
                {RESTORE_STATUS_OPTIONS.map((o) => (
                  <option key={o.value || 'all'} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <Label value="Alcance" className="mb-1" />
              <Select value={restoreScope} onChange={(e) => setRestoreScope(e.target.value)}>
                {RESTORE_SCOPE_OPTIONS.map((o) => (
                  <option key={o.value || 'all-s'} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </Select>
            </div>
            <div className="sm:col-span-2">
              <Label value="Buscar cuenta (email o UUID)" className="mb-1" />
              <TextInput value={restoreSearch} onChange={(e) => setRestoreSearch(e.target.value)} placeholder="ej. sales@" />
            </div>
          </div>
          {canDeleteRestore ? (
            <div>
              <Button
                color="failure"
                outline
                size="sm"
                disabled={bulkDeleteRestore.isPending || deletableRestoreCount === 0}
                onClick={() => void onBulkDeleteRestore()}
              >
                <HiTrash className="h-4 w-4 mr-1 inline" />
                Eliminar listado visible
              </Button>
              <span className="ml-2 text-xs text-slate-500">
                Borra las filas mostradas debajo excepto las que siguen «running».
              </span>
            </div>
          ) : null}
        </div>
        {restoreLoading ? (
          <p className="text-slate-500">Cargando…</p>
        ) : restoreRows.length === 0 ? (
          <p className="text-slate-500">No hay trabajos que coincidan con los filtros.</p>
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
                  <th className="text-right w-40">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {restoreRows.map((j) => (
                  <tr key={j.id} className="border-t border-slate-100 dark:border-slate-800">
                    <td className="py-2">{j.created_at}</td>
                    <td
                      className="max-w-[14rem] truncate text-xs"
                      title={j.account_email ?? j.target_account_id}
                    >
                      {j.account_email ?? `${j.target_account_id.slice(0, 8)}…`}
                    </td>
                    <td className="text-xs" title={j.scope}>
                      {scopeLabel(j.scope)}
                    </td>
                    <td>
                      <Badge color={restoreBadgeColor(j.status)}>{j.status}</Badge>
                    </td>
                    <td>
                      {j.items_restored}/{j.items_total}
                    </td>
                    <td>{j.items_failed}</td>
                    <td className="text-right">
                      <div className="flex justify-end gap-1 flex-wrap">
                        {canCancelRestore && (j.status === 'pending' || j.status === 'running') ? (
                          <Button
                            size="xs"
                            color="failure"
                            disabled={cancelRestore.isPending}
                            onClick={() => void onCancelRestore(j)}
                          >
                            Cancelar
                          </Button>
                        ) : null}
                        {canDeleteRestore && j.status !== 'running' ? (
                          <button
                            type="button"
                            className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/40 border border-red-200 dark:border-red-900/60"
                            title="Eliminar registro"
                            disabled={deleteRestore.isPending}
                            onClick={() => void onDeleteRestore(j)}
                          >
                            <HiX className="h-5 w-5" aria-hidden />
                            <span className="sr-only">Eliminar</span>
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {showVaultMat ? (
        <Card>
          <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
            <div>
              <h2 className="text-lg font-semibold">Materializaciones vault ZIP (Gmail)</h2>
              <p className="text-sm text-slate-500 dark:text-slate-400 mt-1 max-w-3xl">
                Cuando la descarga y extracción terminan en estado <strong>ready</strong>, usá «Llevar a GYB
                trabajo» para fusionar el contenido en <code className="text-xs">/var/msa/work/gmail/&lt;email&gt;/</code> y
                verlo en <Link to="/gyb-work" className="text-blue-600 dark:text-blue-400">GYB trabajo</Link>.
                Los ZIP locales de la sesión se eliminan tras promover.
              </p>
            </div>
            <Link
              to="/vault-gmail-zip"
              className="text-sm text-blue-600 dark:text-blue-400 whitespace-nowrap"
            >
              Nueva materialización
            </Link>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
            <div>
              <Label value="Estado materialización" className="mb-1" />
              <Select value={matStatus} onChange={(e) => setMatStatus(e.target.value)}>
                {MAT_STATUS_OPTIONS.map((o) => (
                  <option key={o.value || 'mall'} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <Label value="Buscar cuenta" className="mb-1" />
              <TextInput value={matSearch} onChange={(e) => setMatSearch(e.target.value)} placeholder="email o UUID" />
            </div>
          </div>
          {matLoading ? (
            <p className="text-slate-500">Cargando materializaciones…</p>
          ) : matRows.length === 0 ? (
            <p className="text-slate-500">No hay sesiones que coincidan con los filtros.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="text-left text-slate-500">
                  <tr>
                    <th className="py-2">Creada</th>
                    <th>Cuenta</th>
                    <th>Ventana / modo</th>
                    <th>ZIPs</th>
                    <th>Estado</th>
                    <th className="text-right">Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {matRows.map((m) => (
                    <tr key={m.id} className="border-t border-slate-100 dark:border-slate-800">
                      <td className="py-2">{m.created_at}</td>
                      <td className="max-w-[14rem] truncate text-xs" title={m.account_email ?? m.account_id}>
                        {m.account_email ?? `${m.account_id.slice(0, 8)}…`}
                      </td>
                      <td className="text-xs whitespace-nowrap">
                        {(m.date_from ?? '—') + ' → ' + (m.date_to ?? '—')} · {m.requested_mode}
                      </td>
                      <td>{materializeZipProgressText(m)}</td>
                      <td>
                        <Badge
                          color={
                            m.status === 'ready' || m.status === 'promoted'
                              ? 'success'
                              : m.status === 'failed'
                                ? 'failure'
                                : m.status === 'pending' || m.status === 'downloading'
                                  ? 'info'
                                  : 'gray'
                          }
                        >
                          {m.status === 'promoted' ? 'en GYB trabajo' : m.status}
                        </Badge>
                      </td>
                      <td className="text-right">
                        <div className="flex justify-end items-center gap-2 flex-wrap">
                          {m.status === 'ready' ? (
                            <Button
                              size="xs"
                              color="blue"
                              disabled={promoteMut.isPending}
                              onClick={() => void promoteRow(m.id)}
                            >
                              Llevar a GYB trabajo
                            </Button>
                          ) : m.status === 'promoted' ? (
                            <Link
                              to={`/gyb-work/${m.account_id}`}
                              className="text-xs text-blue-600 dark:text-blue-400"
                            >
                              Abrir GYB trabajo
                            </Link>
                          ) : null}
                          <button
                            type="button"
                            className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/40 border border-red-200 dark:border-red-900/60"
                            title="Eliminar sesión y datos locales"
                            disabled={deleteMat.isPending}
                            onClick={() => void onDeleteMat(m)}
                          >
                            <HiX className="h-5 w-5" aria-hidden />
                            <span className="sr-only">Eliminar sesión</span>
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      ) : null}
    </div>
  )
}
