import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Badge, Button, Card, Checkbox, Label, TextInput } from 'flowbite-react'
import toast from 'react-hot-toast'
import { HiArrowLeft, HiDownload } from 'react-icons/hi'
import { downloadMaildirExportZip, maildirExportErrorMessage } from '../api/maildirExport'
import { useMailDataInventory, usePurgeAccountMailData } from '../api/hooks'
import { useAuthStore } from '../stores/auth'

function fmtBytes(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return '—'
  if (n < 1024) return `${n} B`
  const kb = n / 1024
  if (kb < 1024) return `${kb.toFixed(1)} KB`
  const mb = kb / 1024
  if (mb < 1024) return `${mb.toFixed(1)} MB`
  return `${(mb / 1024).toFixed(2)} GB`
}

export default function AccountMailDataPage() {
  const { accountId } = useParams<{ accountId: string }>()
  const hasPermission = useAuthStore((s) => s.hasPermission)
  const profile = useAuthStore((s) => s.profile)
  const canPurge = hasPermission('accounts.purge_mail_local')
  const canExportZip =
    hasPermission('mailbox.view_all') ||
    (hasPermission('mailbox.view_delegated') &&
      !!accountId &&
      (profile?.mailbox_delegated_account_ids ?? []).includes(accountId))

  const { data: inv, isLoading, error, refetch } = useMailDataInventory(accountId ?? null)
  const purge = usePurgeAccountMailData()
  const [exportingZip, setExportingZip] = useState(false)

  const [maildir, setMaildir] = useState(false)
  const [gyb, setGyb] = useState(false)
  const [logs, setLogs] = useState(false)
  const [tokens, setTokens] = useState(false)
  const [revokeImap, setRevokeImap] = useState(false)
  const [confirmEmail, setConfirmEmail] = useState('')

  const anythingSelected = maildir || gyb || logs || tokens || revokeImap
  const emailOk =
    inv && confirmEmail.trim().toLowerCase() === inv.email.trim().toLowerCase()

  const errMsg = useMemo(() => {
    if (!error) return null
    const ax = error as { response?: { status?: number; data?: { detail?: string } } }
    const st = ax.response?.status
    const d = ax.response?.data?.detail
    if (st === 403) return 'No tenés permiso (accounts.purge_mail_local).'
    if (typeof d === 'string') return d
    return 'No se pudo cargar el inventario.'
  }, [error])

  async function onPurge() {
    if (!accountId || !inv) return
    if (!anythingSelected) {
      toast.error('Elegí al menos una categoría a eliminar.')
      return
    }
    if (!emailOk) {
      toast.error('El correo de confirmación debe coincidir con la cuenta.')
      return
    }
    try {
      const r = await purge.mutateAsync({
        accountId,
        payload: {
          confirmation_email: confirmEmail.trim(),
          maildir,
          gyb_workdir: gyb,
          gmail_backup_logs: logs,
          webmail_tokens: tokens,
          revoke_imap_credentials: revokeImap,
        },
      })
      toast.success(
        `Purge aplicada: Maildir ${r.maildir_cleared}, GYB ${r.gyb_workdir_cleared}, logs ${r.gmail_logs_deleted}, tokens ${r.webmail_tokens_deleted}.`,
      )
      setMaildir(false)
      setGyb(false)
      setLogs(false)
      setTokens(false)
      setRevokeImap(false)
      setConfirmEmail('')
      void refetch()
    } catch (e) {
      const ax = e as { response?: { status?: number; data?: { detail?: string } } }
      if (ax.response?.status === 403) {
        toast.error('Sin permiso para purgar datos locales.')
      } else {
        const d = ax.response?.data?.detail
        toast.error(typeof d === 'string' ? d : 'No se pudo aplicar la purga.')
      }
    }
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <div className="flex flex-wrap items-center gap-3">
        <Link to="/accounts">
          <Button color="light" size="sm">
            <HiArrowLeft className="h-4 w-4 mr-1" /> Cuentas
          </Button>
        </Link>
        <div>
          <h1 className="text-2xl font-semibold">Datos locales de correo</h1>
          <p className="text-slate-500 text-sm">
            Inventario y borrado selectivo por cuenta Workspace (disco del servidor y registros asociados).
          </p>
        </div>
      </div>

      {!canPurge ? (
        <p className="text-amber-800 dark:text-amber-200 text-sm">
          Tu rol no incluye el permiso <code className="text-xs">accounts.purge_mail_local</code>.
        </p>
      ) : null}

      {isLoading ? <p className="text-slate-500">Cargando inventario…</p> : null}
      {errMsg ? (
        <p className="text-red-600 dark:text-red-400 text-sm">{errMsg}</p>
      ) : null}

      {inv && canPurge ? (
        <>
          <Card>
            <h2 className="font-semibold mb-3">{inv.email}</h2>
            <dl className="grid gap-2 text-sm">
              <div className="flex flex-wrap justify-between gap-2 border-b border-slate-100 dark:border-slate-800 pb-2">
                <dt className="text-slate-500">Maildir local</dt>
                <dd>
                  <code className="text-xs break-all">{inv.maildir_root}</code>
                  <span className="ml-2">
                    {inv.maildir_on_disk ? (
                      <Badge color="success">en disco</Badge>
                    ) : (
                      <Badge color="gray">sin layout</Badge>
                    )}
                  </span>
                  <span className="text-slate-500 ml-2">({fmtBytes(inv.maildir_size_bytes)})</span>
                </dd>
              </div>
              <div className="flex flex-wrap justify-between gap-2 border-b border-slate-100 dark:border-slate-800 pb-2">
                <dt className="text-slate-500">Trabajo GYB</dt>
                <dd>
                  <code className="text-xs break-all">{inv.gyb_work_path}</code>
                  <span className="ml-2">
                    {inv.gyb_work_has_content ? (
                      <Badge color="warning">con archivos</Badge>
                    ) : (
                      <Badge color="gray">vacío</Badge>
                    )}
                  </span>
                  <span className="text-slate-500 ml-2">({fmtBytes(inv.gyb_work_size_bytes)})</span>
                </dd>
              </div>
              <div className="flex flex-wrap justify-between gap-2 border-b border-slate-100 dark:border-slate-800 pb-2">
                <dt className="text-slate-500">Logs de backup Gmail (BD)</dt>
                <dd>{inv.gmail_backup_logs_count}</dd>
              </div>
              <div className="flex flex-wrap justify-between gap-2 border-b border-slate-100 dark:border-slate-800 pb-2">
                <dt className="text-slate-500">Tokens webmail / magic links</dt>
                <dd>{inv.webmail_tokens_count}</dd>
              </div>
              <div className="flex flex-wrap justify-between gap-2">
                <dt className="text-slate-500">IMAP (Roundcube)</dt>
                <dd>
                  {inv.imap_enabled ? <Badge color="success">habilitado</Badge> : <Badge color="gray">no</Badge>}
                  {inv.imap_password_configured ? (
                    <span className="text-slate-500 ml-2">contraseña configurada</span>
                  ) : null}
                </dd>
              </div>
            </dl>
          </Card>

          {canExportZip ? (
            <Card>
              <h2 className="font-semibold mb-2">Exportar copia (.zip)</h2>
              <p className="text-sm text-slate-600 dark:text-slate-400 mb-3">
                Descarga un ZIP con el árbol Maildir tal como está en el servidor (mismas carpetas y ficheros que
                usa Dovecot). Podés extraerlo donde quieras; no depende de Mozilla ni Outlook.
              </p>
              <Button
                color="light"
                disabled={!inv?.maildir_on_disk || exportingZip}
                isProcessing={exportingZip}
                onClick={() => {
                  if (!accountId) return
                  setExportingZip(true)
                  downloadMaildirExportZip(accountId)
                    .then(() => toast.success('Descarga del ZIP iniciada.'))
                    .catch((e) => toast.error(maildirExportErrorMessage(e)))
                    .finally(() => setExportingZip(false))
                }}
              >
                <HiDownload className="h-4 w-4 mr-2" />
                Descargar Maildir (.zip)
              </Button>
              {!inv?.maildir_on_disk ? (
                <p className="text-xs text-slate-500 mt-2">No hay layout Maildir en disco todavía.</p>
              ) : null}
            </Card>
          ) : null}

          <Card className="border-red-200 dark:border-red-900/40">
            <h2 className="font-semibold text-red-800 dark:text-red-300 mb-2">Eliminar seleccionado</h2>
            <p className="text-sm text-slate-600 dark:text-slate-400 mb-4">
              No borra correo en Gmail ni archivos en Drive. Solo datos locales del servidor y registros indicados.
            </p>
            <div className="space-y-3 mb-4">
              <div className="flex items-center gap-2">
                <Checkbox id="p-maildir" checked={maildir} onChange={(e) => setMaildir(e.target.checked)} />
                <Label htmlFor="p-maildir">Vaciar Maildir (buzón local Dovecot)</Label>
              </div>
              <div className="flex items-center gap-2">
                <Checkbox id="p-gyb" checked={gyb} onChange={(e) => setGyb(e.target.checked)} />
                <Label htmlFor="p-gyb">Vaciar carpeta de trabajo GYB</Label>
              </div>
              <div className="flex items-center gap-2">
                <Checkbox id="p-logs" checked={logs} onChange={(e) => setLogs(e.target.checked)} />
                <Label htmlFor="p-logs">Borrar historial de ejecuciones Gmail de esta cuenta (tabla backup_logs)</Label>
              </div>
              <div className="flex items-center gap-2">
                <Checkbox id="p-tok" checked={tokens} onChange={(e) => setTokens(e.target.checked)} />
                <Label htmlFor="p-tok">Invalidar tokens / magic links pendientes</Label>
              </div>
              <div className="flex items-center gap-2">
                <Checkbox id="p-imap" checked={revokeImap} onChange={(e) => setRevokeImap(e.target.checked)} />
                <Label htmlFor="p-imap">Revocar contraseña IMAP y deshabilitar IMAP en la cuenta</Label>
              </div>
            </div>
            <div className="mb-4">
              <Label htmlFor="confirm-mail" value={`Escribí el correo exacto para confirmar: ${inv.email}`} />
              <TextInput
                id="confirm-mail"
                className="mt-1"
                placeholder={inv.email}
                value={confirmEmail}
                onChange={(e) => setConfirmEmail(e.target.value)}
                autoComplete="off"
              />
            </div>
            <Button
              color="failure"
              disabled={!anythingSelected || !emailOk || purge.isPending}
              isProcessing={purge.isPending}
              onClick={() => void onPurge()}
            >
              Aplicar borrado seleccionado
            </Button>
          </Card>
        </>
      ) : null}
    </div>
  )
}
