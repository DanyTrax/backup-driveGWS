import { Badge, Button, Card } from 'flowbite-react'
import toast from 'react-hot-toast'
import api from '../api/client'
import { useAccounts, useClearMailbox, useProvisionMailbox } from '../api/hooks'

function toastProvisionError(err: unknown) {
  const ax = err as { response?: { status?: number; data?: { detail?: unknown } } }
  const st = ax.response?.status
  const d = ax.response?.data?.detail
  const forbidden =
    st === 403 || (typeof d === 'object' && d !== null && (d as { error?: string }).error === 'forbidden')
  if (forbidden) {
    toast.error(
      'No tenés permiso para crear la bandeja. Hace falta permiso de aprobar cuentas o de webmail (SSO / magic link).',
    )
    return
  }
  if (d === 'backup_or_imap_required' || d === 'backup_not_enabled') {
    toast.error('Activá backup o IMAP de gestión para esta cuenta antes de crear la bandeja.')
    return
  }
  if (
    (typeof d === 'object' && d !== null && (d as { error?: string }).error === 'maildir_volume_unavailable') ||
    d === 'maildir_volume_unavailable' ||
    st === 503
  ) {
    const reason =
      typeof d === 'object' && d !== null && 'reason' in d
        ? String((d as { reason?: string }).reason ?? '')
        : ''
    toast.error(
      reason
        ? `Maildir: ${reason.slice(0, 380)}`
        : 'No se pudo escribir en /var/mail/vhosts. Revisá que app y worker monten el volumen maildirs igual que Dovecot y reiniciá los contenedores.',
    )
    return
  }
  if (st === 404 || d === 'account_not_found') {
    toast.error('Cuenta no encontrada.')
    return
  }
  toast.error('No se pudo crear la bandeja. Reintentá o revisá los logs del servidor.')
}

function bandejaLabel(a: {
  maildir_on_disk: boolean
  maildir_user_cleared_at: string | null
}) {
  if (!a.maildir_on_disk) return 'sin carpeta Maildir'
  if (a.maildir_user_cleared_at) return 'vacía (esperando backup Gmail)'
  return 'en disco'
}

export default function WebmailPage() {
  const { data = [] } = useAccounts()
  const provision = useProvisionMailbox()
  const clearMb = useClearMailbox()

  async function ssoAdmin(id: string) {
    try {
      const resp = await api.post(`/webmail/accounts/${id}/sso-admin`)
      window.open(resp.data.url, '_blank', 'noopener')
    } catch {
      toast.error('No se pudo emitir SSO')
    }
  }

  async function provisionMailbox(id: string) {
    try {
      await provision.mutateAsync(id)
      toast.success('Bandeja Maildir creada (lista para Dovecot/Roundcube)')
    } catch (err) {
      toastProvisionError(err)
    }
  }

  async function clearMailbox(id: string) {
    try {
      await clearMb.mutateAsync(id)
      toast.success('Correo local borrado; se repoblará en la próxima tarea Gmail')
    } catch {
      toast.error('No se pudo vaciar la bandeja (requiere backup o IMAP activo)')
    }
  }

  async function issueMagicLink(id: string) {
    try {
      const resp = await api.post(`/webmail/accounts/${id}/magic-link`, {
        purpose: 'first_setup',
      })
      await navigator.clipboard.writeText(resp.data.url)
      toast.success('Magic link copiado al portapapeles')
    } catch {
      toast.error('No se pudo emitir magic link')
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Webmail</h1>
        <p className="text-slate-500">Accede a cualquier buzón o envía un enlace al cliente</p>
      </div>
      <Card>
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="text-left text-slate-500">
              <tr>
                <th className="py-2">Correo</th>
                <th>Backup cuenta</th>
                <th>Bandeja local</th>
                <th>Mensajes (caché)</th>
                <th>IMAP gestión</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {data.map((a) => (
                <tr key={a.id} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="py-2 font-medium">{a.email}</td>
                  <td>
                    {a.is_backup_enabled ? (
                      <Badge color="success">conectado</Badge>
                    ) : (
                      <Badge color="gray">desconectado</Badge>
                    )}
                  </td>
                  <td className="text-xs">{bandejaLabel(a)}</td>
                  <td>{a.maildir_user_cleared_at ? '0' : (a.total_messages_cache ?? '—')}</td>
                  <td>{a.imap_enabled ? 'sí' : 'no'}</td>
                  <td className="text-right space-x-2 flex flex-wrap justify-end gap-2">
                    <Button
                      size="xs"
                      color="light"
                      disabled={
                        !(a.is_backup_enabled || a.imap_enabled) || provision.isPending
                      }
                      onClick={() => provisionMailbox(a.id)}
                    >
                      Crear bandeja
                    </Button>
                    <Button
                      size="xs"
                      color="failure"
                      disabled={
                        (!a.imap_enabled && !a.is_backup_enabled) || clearMb.isPending
                      }
                      onClick={() => clearMailbox(a.id)}
                    >
                      Vaciar correo local
                    </Button>
                    <Button size="xs" color="light" onClick={() => issueMagicLink(a.id)}>
                      Generar magic link
                    </Button>
                    <Button size="xs" onClick={() => ssoAdmin(a.id)}>
                      Entrar como admin
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
