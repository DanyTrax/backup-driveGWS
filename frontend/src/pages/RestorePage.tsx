import { Badge, Button, Card } from 'flowbite-react'
import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import type { AxiosError } from 'axios'

import {
  useGmailVaultMaterializeRecent,
  useProfile,
  usePromoteGmailVaultMaterialize,
  useRestoreJobs,
} from '../api/hooks'
import type { GmailVaultMaterializeListItem } from '../api/types'

function formatApiErr(err: unknown): string {
  const ax = err as AxiosError<{ detail?: unknown }>
  const d = ax.response?.data?.detail
  if (typeof d === 'string') return d
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

export default function RestorePage() {
  const { data = [], isLoading } = useRestoreJobs()
  const { data: profile } = useProfile()
  const showVaultMat =
    Boolean(profile?.permissions?.includes('vault_drive.view_all')) ||
    Boolean(profile?.permissions?.includes('vault_drive.view_delegated'))
  const { data: matRecent = [], isLoading: matLoading } = useGmailVaultMaterializeRecent({
    enabled: showVaultMat,
  })
  const promoteMut = usePromoteGmailVaultMaterialize()

  async function promoteRow(id: string) {
    try {
      await promoteMut.mutateAsync(id)
      toast.success('Datos fusionados en la carpeta GYB trabajo para esa cuenta.')
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

      {showVaultMat ? (
        <Card>
          <div className="flex flex-wrap items-start justify-between gap-3 mb-2">
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
          {matLoading ? (
            <p className="text-slate-500">Cargando materializaciones…</p>
          ) : matRecent.length === 0 ? (
            <p className="text-slate-500">No hay sesiones de materialización recientes.</p>
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
                    <th className="text-right">Acción</th>
                  </tr>
                </thead>
                <tbody>
                  {matRecent.map((m) => (
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
                        ) : (
                          <span className="text-slate-400">—</span>
                        )}
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
