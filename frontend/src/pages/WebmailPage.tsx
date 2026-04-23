import { Button, Card } from 'flowbite-react'
import toast from 'react-hot-toast'
import api from '../api/client'
import { useAccounts, useProvisionMailbox } from '../api/hooks'

export default function WebmailPage() {
  const { data = [] } = useAccounts(true)
  const provision = useProvisionMailbox()

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
    } catch {
      toast.error('Solo cuentas con backup activo pueden aprovisionar bandeja')
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
                <th>Mensajes en respaldo</th>
                <th>Webmail listo</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {data.map((a) => (
                <tr key={a.id} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="py-2 font-medium">{a.email}</td>
                  <td>{a.total_messages_cache ?? '—'}</td>
                  <td>{a.imap_enabled ? 'sí' : 'no'}</td>
                  <td className="text-right space-x-2 flex flex-wrap justify-end gap-2">
                    <Button
                      size="xs"
                      color="light"
                      disabled={!a.is_backup_enabled || provision.isPending}
                      onClick={() => provisionMailbox(a.id)}
                    >
                      Crear bandeja
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
