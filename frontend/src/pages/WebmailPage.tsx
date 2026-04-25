import { useState } from 'react'
import type { AxiosError } from 'axios'
import { Badge, Button, Card, Label, Modal, Select, TextInput } from 'flowbite-react'
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

/** Cuerpo `detail` de FastAPI: string, lista de validación, u objeto. */
function formatApiDetail(detail: unknown): string | null {
  if (detail == null) return null
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const parts = detail.map((item) => {
      if (typeof item === 'object' && item !== null && 'msg' in item) {
        return String((item as { msg: string }).msg)
      }
      return String(item)
    })
    return parts.length ? parts.join('; ') : null
  }
  if (typeof detail === 'object') {
    const o = detail as { message?: unknown; error?: unknown }
    if (o.message != null) return String(o.message)
    if (o.error != null) return String(o.error)
  }
  return null
}

/**
 * Muestra el error real de la API (403/422/5xx) para acortar diagnóstico (SSO, permisos, Redis).
 */
function toastWebmailApiError(err: unknown, fallback: string) {
  const ax = err as AxiosError<{ detail?: unknown }>
  const st = ax.response?.status
  const raw = ax.response?.data?.detail
  const msg = formatApiDetail(raw)
  if (st === 403) {
    const d = (typeof raw === 'string' ? raw : '').toLowerCase()
    if (d === 'forbidden' || !msg) {
      toast.error(
        'No tenés permiso para esta acción. «Entrar como admin» requiere webmail.sso_admin; magic link, enlace de asignación y fijar contraseña requieren webmail.issue_magic_link (p. ej. operador o super admin, no el rol solo-auditor).',
      )
      return
    }
    toast.error(msg.length > 500 ? msg.slice(0, 497) + '…' : msg)
    return
  }
  if (st === 422 && msg) {
    toast.error(msg.length > 500 ? msg.slice(0, 497) + '…' : msg)
    return
  }
  if (msg) {
    toast.error(msg.length > 500 ? msg.slice(0, 497) + '…' : msg)
    return
  }
  if (st && st >= 500) {
    toast.error('Error del servidor (p. ej. Redis o base de datos). Revisá los logs del contenedor app.')
    return
  }
  if (!ax.response) {
    toast.error('Sin respuesta del servidor (red o timeout).')
    return
  }
  toast.error(fallback)
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

  const [localPwdId, setLocalPwdId] = useState<string | null>(null)
  const [localPwd, setLocalPwd] = useState('')
  const [localPwd2, setLocalPwd2] = useState('')
  const [savingPwd, setSavingPwd] = useState(false)

  const [assignLinkId, setAssignLinkId] = useState<string | null>(null)
  const [ttlHours, setTtlHours] = useState(24)
  const [issuedUrl, setIssuedUrl] = useState<string | null>(null)
  const [issuedExp, setIssuedExp] = useState<string | null>(null)
  const [issuingLink, setIssuingLink] = useState(false)

  function openLocalPwd(id: string) {
    setLocalPwdId(id)
    setLocalPwd('')
    setLocalPwd2('')
  }

  function openAssignLink(id: string) {
    setAssignLinkId(id)
    setTtlHours(24)
    setIssuedUrl(null)
    setIssuedExp(null)
  }

  async function submitLocalPwd() {
    if (!localPwdId) return
    if (localPwd.length < 10) {
      toast.error('La contraseña debe tener al menos 10 caracteres.')
      return
    }
    if (localPwd !== localPwd2) {
      toast.error('Las contraseñas no coinciden.')
      return
    }
    setSavingPwd(true)
    try {
      await api.post(`/webmail/accounts/${localPwdId}/password`, { new_password: localPwd })
      toast.success('Contraseña IMAP / webmail guardada para esta cuenta')
      setLocalPwdId(null)
    } catch (err) {
      toastWebmailApiError(err, 'No se pudo guardar la contraseña.')
    } finally {
      setSavingPwd(false)
    }
  }

  async function submitAssignLink() {
    if (!assignLinkId) return
    setIssuingLink(true)
    setIssuedUrl(null)
    setIssuedExp(null)
    try {
      const resp = await api.post<{
        url: string
        expires_at: string
        ttl_minutes: number
      }>(`/webmail/accounts/${assignLinkId}/password-assign-link`, { ttl_hours: ttlHours })
      setIssuedUrl(resp.data.url)
      setIssuedExp(resp.data.expires_at)
      await navigator.clipboard.writeText(resp.data.url)
      toast.success('Enlace copiado al portapapeles')
    } catch (err) {
      toastWebmailApiError(err, 'No se pudo generar el enlace de asignación.')
    } finally {
      setIssuingLink(false)
    }
  }

  async function ssoAdmin(id: string) {
    try {
      const resp = await api.post(`/webmail/accounts/${id}/sso-admin`)
      window.open(resp.data.url, '_blank', 'noopener')
    } catch (err) {
      toastWebmailApiError(err, 'No se pudo emitir SSO (revisá permisos o logs del servidor).')
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
    } catch (err) {
      toastWebmailApiError(err, 'No se pudo vaciar la bandeja (requiere backup o IMAP activo).')
    }
  }

  async function issueMagicLink(id: string) {
    try {
      const resp = await api.post(`/webmail/accounts/${id}/magic-link`, {
        purpose: 'first_setup',
      })
      await navigator.clipboard.writeText(resp.data.url)
      toast.success('Magic link copiado al portapapeles')
    } catch (err) {
      toastWebmailApiError(err, 'No se pudo emitir el magic link.')
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Webmail</h1>
        <p className="text-slate-500 text-sm mt-2 max-w-3xl">
          <strong>Fijar contraseña (local)</strong> escribe un hash en PostgreSQL (Dovecot lo lee); no usa <code className="text-xs">SECRET_KEY</code> ni
          un «token de .env» para el login en webmail, solo el correo y la clave que guardes. <strong>Enlace asignar clave</strong>{' '}
          y el token de <strong>Magic link (Roundcube)</strong> (first setup / reset) también sirven en la misma
          pantalla pública de asignación si al usuario solo le pasan el <code className="text-xs">?token=</code>. Tras
          fijar la clave, en Roundcube el usuario es el correo de la tabla (mismo dominio). <strong>Entrar como admin</strong>{' '}
          (SSO) sí usa <code className="text-xs">DOVECOT_MASTER_*</code> y Redis.
        </p>
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
                      Magic link (Roundcube)
                    </Button>
                    <Button size="xs" color="light" onClick={() => openLocalPwd(a.id)}>
                      Fijar contraseña (local)
                    </Button>
                    <Button size="xs" color="light" onClick={() => openAssignLink(a.id)}>
                      Enlace asignar clave
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

      <Modal show={localPwdId !== null} onClose={() => setLocalPwdId(null)} size="md">
        <Modal.Header>Contraseña IMAP / webmail</Modal.Header>
        <Modal.Body className="space-y-3">
          <p className="text-sm text-slate-600 dark:text-slate-300">
            Se guarda el hash de la clave en la base (tabla de cuentas), no en variables <code className="text-xs">SECRET_KEY</code> /{' '}
            <code className="text-xs">FERNET</code> del <code className="text-xs">.env</code> (esas son para la API y cifrado
            de secretos, no para la contraseña IMAP). Mínimo 10 caracteres. En Roundcube usá el correo{' '}
            <strong>exactamente</strong> como en la tabla.
          </p>
          <div>
            <Label value="Nueva contraseña" />
            <TextInput
              type="password"
              value={localPwd}
              onChange={(e) => setLocalPwd(e.target.value)}
              minLength={10}
              autoComplete="new-password"
            />
          </div>
          <div>
            <Label value="Repetir" />
            <TextInput
              type="password"
              value={localPwd2}
              onChange={(e) => setLocalPwd2(e.target.value)}
              minLength={10}
            />
          </div>
        </Modal.Body>
        <Modal.Footer>
          <Button color="gray" onClick={() => setLocalPwdId(null)}>
            Cancelar
          </Button>
          <Button onClick={() => void submitLocalPwd()} disabled={savingPwd}>
            {savingPwd ? 'Guardando…' : 'Guardar'}
          </Button>
        </Modal.Footer>
      </Modal>

      <Modal show={assignLinkId !== null} onClose={() => setAssignLinkId(null)} size="lg">
        <Modal.Header>Enlace para que el usuario asigne su contraseña</Modal.Header>
        <Modal.Body className="space-y-3">
          <p className="text-sm text-slate-600 dark:text-slate-300">
            El enlace abre la misma pantalla pública que si copiás solo el <code className="text-xs">token</code> del magic
            link a Roundcube (first setup / reset). Vigencia máxima 24 h para este botón; al vencer queda inválido.
          </p>
          <div className="max-w-xs">
            <Label value="Validez del enlace (horas)" />
            <Select
              value={String(ttlHours)}
              onChange={(e) => setTtlHours(Number(e.target.value))}
            >
              {[1, 2, 4, 8, 12, 18, 24].map((h) => (
                <option key={h} value={h}>
                  {h} h
                </option>
              ))}
            </Select>
          </div>
          {issuedUrl && (
            <div className="text-xs break-all p-2 rounded bg-slate-100 dark:bg-slate-800">
              <strong>URL:</strong> {issuedUrl}
              {issuedExp && (
                <p className="mt-1 text-slate-500">Caduca: {new Date(issuedExp).toLocaleString()}</p>
              )}
            </div>
          )}
        </Modal.Body>
        <Modal.Footer>
          <Button color="gray" onClick={() => setAssignLinkId(null)}>
            Cerrar
          </Button>
          <Button onClick={() => void submitAssignLink()} disabled={issuingLink}>
            {issuingLink ? 'Generando…' : issuedUrl ? 'Generar otro' : 'Generar y copiar'}
          </Button>
        </Modal.Footer>
      </Modal>
    </div>
  )
}
