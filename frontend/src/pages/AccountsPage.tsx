import { useMemo, useRef, useState } from 'react'
import type { AxiosError } from 'axios'
import { Link } from 'react-router-dom'
import { Badge, Button, Card, Modal, TextInput, ToggleSwitch } from 'flowbite-react'
import { HiSearch, HiRefresh } from 'react-icons/hi'
import toast from 'react-hot-toast'
import {
  useAccounts,
  useApproveAccount,
  useRevokeAccount,
  useStartVerifyAccessStream,
  useSyncAccounts,
} from '../api/hooks'
import type { AccountAccessCheck, WorkspaceAccount } from '../api/types'
import { useAuthStore } from '../stores/auth'
import { hideMaildirWebmailUi } from '../config/ui'

function canOpenMailbox(
  account: WorkspaceAccount,
  hasPermission: (code: string) => boolean,
  delegatedIds: Set<string>,
): boolean {
  if (!account.maildir_on_disk || account.maildir_user_cleared_at) return false
  if (hasPermission('mailbox.view_all')) return true
  if (hasPermission('mailbox.view_delegated') && delegatedIds.has(account.id)) return true
  return false
}

function canOpenVaultDrive(
  account: WorkspaceAccount,
  hasPermission: (code: string) => boolean,
  delegatedVaultIds: Set<string>,
): boolean {
  if (!(account.drive_vault_folder_id ?? '').trim()) return false
  if (hasPermission('vault_drive.view_all')) return true
  if (hasPermission('vault_drive.view_delegated') && delegatedVaultIds.has(account.id)) return true
  return false
}

/** Mensajes GYB leídos desde 1-GMAIL/gyb_mbox vía rclone (no requiere carpeta de trabajo local). */
function canOpenGybVaultMailbox(
  account: WorkspaceAccount,
  hasPermission: (code: string) => boolean,
  delegatedMailboxIds: Set<string>,
): boolean {
  if (!(account.drive_vault_folder_id ?? '').trim()) return false
  if (hasPermission('mailbox.view_all')) return true
  if (hasPermission('mailbox.view_delegated') && delegatedMailboxIds.has(account.id)) return true
  return false
}

function verifyAccessErrorMessage(err: unknown): string {
  const ax = err as AxiosError<{ detail?: unknown }>
  if (ax.code === 'ECONNABORTED') {
    return 'Tiempo de espera agotado en el navegador. La parte Gmail puede tardar varios minutos; reintentá o ampliá el proxy (NPM) si corta antes de 6 min.'
  }
  const st = ax.response?.status
  const d = ax.response?.data?.detail
  if (st === 403) {
    return 'Sin permiso (accounts.view). Pedí acceso de operador o auditor al administrador.'
  }
  if (st === 404) return 'Cuenta no encontrada.'
  if (typeof d === 'string') return d.length > 280 ? `${d.slice(0, 280)}…` : d
  if (d && typeof d === 'object' && 'error' in d) {
    const o = d as { error?: string }
    if (o.error) return o.error
  }
  return ax.message || 'Error de red o del servidor. Revisá la consola de red (F12).'
}

type LiveVerifyState = {
  accountId: string
  accountEmail: string
  streaming: boolean
  progressPct: number
  message: string
  gmailActivity: string
  result: AccountAccessCheck | null
  error: string | null
}

export default function AccountsPage() {
  const [search, setSearch] = useState('')
  const [onlyEnabled, setOnlyEnabled] = useState(false)
  const { data = [], isLoading } = useAccounts(onlyEnabled || undefined)
  const sync = useSyncAccounts()
  const approve = useApproveAccount()
  const revoke = useRevokeAccount()
  const startStream = useStartVerifyAccessStream()
  const [liveVerify, setLiveVerify] = useState<LiveVerifyState | null>(null)
  const wsRef = useRef<WebSocket | null>(null)

  const hasPermission = useAuthStore((s) => s.hasPermission)
  const profile = useAuthStore((s) => s.profile)
  const delegatedMailboxIds = useMemo(
    () => new Set(profile?.mailbox_delegated_account_ids ?? []),
    [profile?.mailbox_delegated_account_ids],
  )
  const delegatedVaultIds = useMemo(
    () => new Set(profile?.vault_drive_delegated_account_ids ?? []),
    [profile?.vault_drive_delegated_account_ids],
  )
  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase()
    if (!term) return data
    return data.filter(
      (a) =>
        a.email.toLowerCase().includes(term) ||
        (a.full_name ?? '').toLowerCase().includes(term) ||
        (a.org_unit_path ?? '').toLowerCase().includes(term),
    )
  }, [data, search])

  function closeVerifyModal() {
    wsRef.current?.close()
    wsRef.current = null
    setLiveVerify(null)
  }

  async function onComprobar(a: WorkspaceAccount) {
    const token = useAuthStore.getState().accessToken
    if (!token) {
      toast.error('Sesión expirada')
      return
    }
    wsRef.current?.close()
    wsRef.current = null
    setLiveVerify({
      accountId: a.id,
      accountEmail: a.email,
      streaming: true,
      progressPct: 0,
      message: 'Conectando…',
      gmailActivity: '',
      result: null,
      error: null,
    })
    try {
      const { session_id } = await startStream.mutateAsync(a.id)
      const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const wsUrl = `${proto}//${window.location.host}/api/backup/ws/progress/${encodeURIComponent(session_id)}?token=${encodeURIComponent(token)}`
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws
      ws.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data as string) as Record<string, unknown>
          if (data.stage !== 'verify_access') return
          const phase = data.phase as string | undefined
          const pct =
            typeof data.progress_pct === 'number' ? (data.progress_pct as number) : undefined
          const msg = typeof data.message === 'string' ? (data.message as string) : ''
          setLiveVerify((prev) => {
            if (!prev) return null
            const next = { ...prev }
            if (pct !== undefined) next.progressPct = pct
            if (msg) next.message = msg
            if (typeof data.gmail_activity === 'string')
              next.gmailActivity = data.gmail_activity as string
            return next
          })
          if (phase === 'complete' && data.result && typeof data.result === 'object') {
            setLiveVerify((prev) =>
              prev
                ? {
                    ...prev,
                    streaming: false,
                    progressPct: 100,
                    result: data.result as AccountAccessCheck,
                  }
                : null,
            )
            ws.close()
            wsRef.current = null
          }
          if (phase === 'error') {
            const errMsg =
              typeof data.message === 'string' ? (data.message as string) : 'Error en comprobación'
            setLiveVerify((prev) =>
              prev ? { ...prev, streaming: false, error: errMsg, progressPct: prev.progressPct } : null,
            )
            toast.error(errMsg.length > 200 ? `${errMsg.slice(0, 200)}…` : errMsg)
            ws.close()
            wsRef.current = null
          }
        } catch {
          /* JSON inválido */
        }
      }
      ws.onerror = () => {
        setLiveVerify((prev) =>
          prev
            ? {
                ...prev,
                streaming: false,
                error:
                  'WebSocket bloqueado o mal proxificado. En Nginx Proxy Manager, en el host de la plataforma, Advanced: agregá un bloque location /api/backup/ws/ con Upgrade y Connection upgrade (ver docs/deployment/NPM-proxy-hosts.md).',
              }
            : null,
        )
        toast.error('WebSocket no disponible: revisá el proxy (NPM) para /api/backup/ws/')
        wsRef.current = null
      }
    } catch (err) {
      setLiveVerify((prev) =>
        prev
          ? { ...prev, streaming: false, error: verifyAccessErrorMessage(err) }
          : null,
      )
      toast.error(verifyAccessErrorMessage(err))
    }
  }

  async function onSync() {
    await sync.mutateAsync()
    toast.success('Sincronización con Workspace completada')
  }

  const showModal = liveVerify !== null
  const result = liveVerify?.result

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Cuentas de Workspace</h1>
          <p className="text-slate-500">Opt-in por cuenta y provisión del vault</p>
        </div>
        <Button onClick={onSync} isProcessing={sync.isPending}>
          <HiRefresh className="h-5 w-5 mr-2" /> Sincronizar directorio
        </Button>
      </div>

      <Card>
        <div className="flex items-center gap-4 flex-wrap">
          <TextInput
            icon={HiSearch}
            placeholder="Buscar por correo, nombre o unidad organizativa"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="flex-1 min-w-[280px]"
          />
          <ToggleSwitch
            checked={onlyEnabled}
            onChange={setOnlyEnabled}
            label="Solo con backup activo"
          />
        </div>
      </Card>

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
                  <th>OU</th>
                  <th>Estado Workspace</th>
                  <th>Backup</th>
                  <th>IMAP</th>
                  <th>Bandeja local</th>
                  <th>GYB / bandeja</th>
                  <th>Bóveda Drive</th>
                  <th>Datos locales</th>
                  <th>Último backup</th>
                  <th>Acceso</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((a) => (
                  <tr key={a.id} className="border-t border-slate-100 dark:border-slate-800">
                    <td className="py-2 font-medium">{a.email}</td>
                    <td>{a.full_name ?? '—'}</td>
                    <td className="text-xs text-slate-500">{a.org_unit_path ?? '—'}</td>
                    <td>
                      <Badge
                        color={
                          a.workspace_status === 'discovered'
                            ? 'info'
                            : a.workspace_status === 'deleted_in_workspace'
                              ? 'failure'
                              : 'warning'
                        }
                      >
                        {a.workspace_status}
                      </Badge>
                    </td>
                    <td>
                      {a.is_backup_enabled ? (
                        <Badge color="success">activo</Badge>
                      ) : (
                        <Badge color="gray">inactivo</Badge>
                      )}
                    </td>
                    <td>
                      {a.imap_enabled ? (
                        <Badge color="success">sí</Badge>
                      ) : (
                        <Badge color="gray">no</Badge>
                      )}
                    </td>
                    <td className="text-xs text-slate-600 dark:text-slate-400 max-w-[10rem]">
                      {!a.maildir_on_disk
                        ? 'sin carpeta'
                        : a.maildir_user_cleared_at
                          ? 'vacía (sync Gmail)'
                          : 'en disco'}
                    </td>
                    <td>
                      {hideMaildirWebmailUi() ? (
                        <div className="flex flex-wrap gap-1 justify-start">
                          {a.is_backup_enabled ? (
                            <Link to={`/gyb-work/${a.id}`}>
                              <Button size="xs" color="light">
                                GYB local
                              </Button>
                            </Link>
                          ) : null}
                          {canOpenGybVaultMailbox(a, hasPermission, delegatedMailboxIds) ? (
                            <Link to={`/gyb-vault-work/${a.id}`}>
                              <Button size="xs" color="light">
                                GYB en Drive
                              </Button>
                            </Link>
                          ) : null}
                          {!a.is_backup_enabled &&
                          !canOpenGybVaultMailbox(a, hasPermission, delegatedMailboxIds) ? (
                            <span className="text-slate-400 text-xs">—</span>
                          ) : null}
                        </div>
                      ) : canOpenMailbox(a, hasPermission, delegatedMailboxIds) ? (
                        <Link to={`/accounts/${a.id}/mailbox`}>
                          <Button size="xs" color="light">
                            Ver correo
                          </Button>
                        </Link>
                      ) : (
                        <span className="text-slate-400 text-xs">—</span>
                      )}
                    </td>
                    <td>
                      {canOpenVaultDrive(a, hasPermission, delegatedVaultIds) ? (
                        <Link to={`/vault-drive/${a.id}`}>
                          <Button size="xs" color="light">
                            Bóveda
                          </Button>
                        </Link>
                      ) : (
                        <span className="text-slate-400 text-xs">—</span>
                      )}
                    </td>
                    <td>
                      {hasPermission('accounts.purge_mail_local') ? (
                        <Link to={`/accounts/${a.id}/mail-data`}>
                          <Button size="xs" color="light">
                            Gestionar
                          </Button>
                        </Link>
                      ) : (
                        <span className="text-slate-400 text-xs">—</span>
                      )}
                    </td>
                    <td className="text-xs text-slate-500">
                      {a.last_successful_backup_at ?? '—'}
                    </td>
                    <td>
                      <Button
                        size="xs"
                        color="light"
                        isProcessing={
                          startStream.isPending ||
                          (!!liveVerify?.streaming && liveVerify.accountId === a.id)
                        }
                        onClick={() => void onComprobar(a)}
                      >
                        Comprobar
                      </Button>
                    </td>
                    <td className="space-x-2 text-right">
                      {a.is_backup_enabled ? (
                        <Button
                          size="xs"
                          color="light"
                          onClick={() =>
                            revoke.mutate(a.id, {
                              onSuccess: () => toast('Backup desactivado'),
                            })
                          }
                        >
                          Desactivar
                        </Button>
                      ) : (
                        <Button
                          size="xs"
                          onClick={() =>
                            approve.mutate(a.id, {
                              onSuccess: () => toast.success('Backup activado'),
                              onError: () => toast.error('No se pudo activar'),
                            })
                          }
                          disabled={a.workspace_status === 'deleted_in_workspace'}
                        >
                          Activar backup
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Modal show={showModal} onClose={closeVerifyModal} size="xl">
        <Modal.Header>Comprobación de acceso</Modal.Header>
        <Modal.Body className="space-y-4 text-sm max-h-[75vh] overflow-y-auto">
          {liveVerify && (
            <>
              <p className="text-slate-600 dark:text-slate-400">{liveVerify.accountEmail}</p>

              {(liveVerify.streaming || (!liveVerify.result && !liveVerify.error)) && (
                <div className="space-y-2 rounded-lg border border-slate-200 dark:border-slate-700 p-3 bg-slate-50/80 dark:bg-slate-900/40">
                  <div className="flex justify-between text-xs text-slate-600 dark:text-slate-400">
                    <span>Progreso estimado</span>
                    <span>{Math.round(liveVerify.progressPct)}%</span>
                  </div>
                  <div className="w-full bg-slate-200 rounded-full h-2.5 dark:bg-slate-700 overflow-hidden">
                    <div
                      className="bg-blue-600 h-2.5 rounded-full transition-all duration-300 ease-out"
                      style={{ width: `${Math.min(100, Math.max(0, liveVerify.progressPct))}%` }}
                    />
                  </div>
                  <p className="text-xs text-slate-700 dark:text-slate-300">{liveVerify.message}</p>
                  {liveVerify.gmailActivity ? (
                    <pre className="text-[11px] whitespace-pre-wrap break-words bg-slate-100 dark:bg-slate-950 p-2 rounded max-h-24 overflow-y-auto font-mono opacity-90">
                      {liveVerify.gmailActivity}
                    </pre>
                  ) : null}
                  {liveVerify.streaming ? (
                    <p className="text-xs text-slate-500">
                      Los eventos llegan en vivo por WebSocket. La fase Gmail (GYB) suele ser la más
                      larga.
                    </p>
                  ) : null}
                </div>
              )}

              {liveVerify.error && !liveVerify.result ? (
                <div className="rounded-lg border border-red-200 dark:border-red-900/50 bg-red-50/50 dark:bg-red-950/20 p-3 text-red-800 dark:text-red-200 text-xs whitespace-pre-wrap">
                  {liveVerify.error}
                </div>
              ) : null}

              {result ? (
                <>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="rounded-lg border border-slate-200 dark:border-slate-700 p-3">
                      <div className="font-medium mb-1">Google Drive</div>
                      <Badge color={result.drive_ok ? 'success' : 'failure'}>
                        {result.drive_ok ? 'OK' : 'Fallo'}
                      </Badge>
                      <pre className="mt-2 text-xs whitespace-pre-wrap break-words bg-slate-50 dark:bg-slate-900 p-2 rounded max-h-40 overflow-y-auto">
                        {result.drive_detail ?? '—'}
                      </pre>
                    </div>
                    <div className="rounded-lg border border-slate-200 dark:border-slate-700 p-3">
                      <div className="font-medium mb-1">Gmail (API / GYB)</div>
                      <Badge color={result.gmail_ok ? 'success' : 'failure'}>
                        {result.gmail_ok ? 'OK' : 'Fallo'}
                      </Badge>
                      <pre className="mt-2 text-xs whitespace-pre-wrap break-words bg-slate-50 dark:bg-slate-900 p-2 rounded max-h-40 overflow-y-auto">
                        {result.gmail_detail ?? '—'}
                      </pre>
                    </div>
                  </div>
                  <div className="rounded-lg border border-slate-200 dark:border-slate-700 p-3">
                    <div className="font-medium mb-1">Maildir en el servidor (Dovecot)</div>
                    <Badge color={result.maildir_layout_ok ? 'success' : 'warning'}>
                      {result.maildir_layout_ok ? 'cur/new/tmp OK' : 'Sin layout completo'}
                    </Badge>
                    <p className="mt-2 text-xs font-mono break-all">{result.maildir_path ?? '—'}</p>
                    <p className="mt-2 text-xs text-slate-500">
                      Indica si la carpeta Maildir existe en disco; el contenido depende del último backup
                      Gmail.
                    </p>
                  </div>
                </>
              ) : null}
            </>
          )}
        </Modal.Body>
        <Modal.Footer>
          <Button color="gray" onClick={closeVerifyModal}>
            Cerrar
          </Button>
        </Modal.Footer>
      </Modal>
    </div>
  )
}
