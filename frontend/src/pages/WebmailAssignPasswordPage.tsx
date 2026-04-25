import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { HiEye, HiEyeOff } from 'react-icons/hi'
import { Alert, Button, Card, Label, Spinner, TextInput } from 'flowbite-react'
import toast from 'react-hot-toast'
import publicClient from '../api/publicClient'
import type { AxiosError } from 'axios'

type Status = 'loading' | 'ready' | 'invalid' | 'done'

type PeekReason = string | null

export default function WebmailAssignPasswordPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const token = (searchParams.get('token') ?? '').trim()
  const [status, setStatus] = useState<Status>('loading')
  const [invalidReason, setInvalidReason] = useState<PeekReason>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [email, setEmail] = useState<string | null>(null)
  const [expiresAt, setExpiresAt] = useState<string | null>(null)
  const [pw, setPw] = useState('')
  const [pw2, setPw2] = useState('')
  const [show, setShow] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!token) {
      setStatus('invalid')
      setInvalidReason('not_found')
      return
    }
    setStatus('loading')
    setLoadError(null)
    try {
      const resp = await publicClient.get<{
        ok: boolean
        email: string | null
        expires_at: string | null
        reason: string | null
      }>('/webmail/password-setup/status', { params: { token } })
      if (resp.data.ok && resp.data.email && resp.data.expires_at) {
        setEmail(resp.data.email)
        setExpiresAt(resp.data.expires_at)
        setStatus('ready')
        return
      }
      setStatus('invalid')
      setInvalidReason(resp.data.reason ?? 'not_found')
      if (resp.data.email) setEmail(resp.data.email)
    } catch (e) {
      const ax = e as AxiosError
      if (ax.response?.status === 429) {
        setStatus('invalid')
        setLoadError('Demasiados intentos. Reintentá en una hora o probá otra red.')
        return
      }
      setStatus('invalid')
      setLoadError('No se pudo comprobar el enlace. Revisá conexión o que este sitio sea el de la plataforma (mismo origen que /api).')
    }
  }, [token])

  useEffect(() => {
    void load()
  }, [load])

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setFormError(null)
    if (pw.length < 10) {
      setFormError('La contraseña debe tener al menos 10 caracteres.')
      return
    }
    if (pw !== pw2) {
      setFormError('Las contraseñas no coinciden.')
      return
    }
    setSubmitting(true)
    try {
      await publicClient.post('/webmail/password-setup/complete', { token, new_password: pw })
      setStatus('done')
      toast.success('Contraseña de webmail / IMAP guardada')
    } catch (err) {
      const ax = err as { response?: { status?: number; data?: { detail?: unknown } } }
      const d = ax.response?.data?.detail
      if (ax.response?.status === 429) {
        setFormError('Demasiados intentos. Reintentá en un rato.')
        return
      }
      if (d === 'token_expired' || d === 'invalid_or_expired_token' || d === 'invalid_token') {
        setFormError('El enlace expiró o ya no es válido. Pedí uno nuevo a tu administrador.')
        return
      }
      if (d === 'token_already_used') {
        setFormError('Este enlace ya se usó. Entrá a webmail con correo y la contraseña que definiste.')
        return
      }
      if (d === 'password_too_short') {
        setFormError('La contraseña es demasiado corta (mínimo 10 caracteres).')
        return
      }
      setFormError('No se pudo guardar la contraseña. Reintentá o pedí un enlace nuevo.')
    } finally {
      setSubmitting(false)
    }
  }

  function invalidMessage(): string {
    if (loadError) return loadError
    switch (invalidReason) {
      case 'consumed':
        return 'Este enlace ya se usó (si ya fijaste la clave, entrá a webmail con tu correo y contraseña). Pedí un enlace nuevo solo si hace falta volver a cambiarla.'
      case 'expired':
        return 'El enlace venció. Pedí a tu administrador un enlace nuevo (hasta 24 h de validez).'
      case 'not_found':
        return 'No encontramos el token (copiá el enlace completo o abrí el mail original).'
      case 'revoked':
        return 'El enlace fue revocado. Generá otro desde el panel.'
      case 'wrong_purpose':
        return 'Este token no corresponde a asignar clave (p. ej. es de acceso «cliente SSO» u otro flujo). Generá en el panel un enlace con «Enlace asignar clave» o fijá la clave con «Fijar contraseña (local)».'
      case 'no_account':
        return 'La cuenta asociada ya no existe en el sistema.'
      default:
        return 'El enlace venció, ya se usó o no existe. Contactá a tu administrador para generar un enlace de asignación (hasta 24 h).'
    }
  }

  if (status === 'loading') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-800 to-slate-900 p-4">
        <Spinner size="lg" className="fill-blue-500" />
      </div>
    )
  }

  if (status === 'invalid' && !formError) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-800 to-slate-900 p-4">
        <Card className="w-full max-w-md">
          <h1 className="text-xl font-semibold text-slate-900 dark:text-white">No se puede usar este enlace</h1>
          <p className="text-sm text-slate-600 dark:text-slate-300 mt-2">{invalidMessage()}</p>
          {email && (invalidReason === 'consumed' || invalidReason === 'expired') && (
            <p className="text-xs text-slate-500 mt-2 break-all">Cuenta: {email}</p>
          )}
          <Button className="mt-4" color="light" onClick={() => navigate('/login')}>
            Ir al inicio de sesión
          </Button>
        </Card>
      </div>
    )
  }

  if (status === 'done') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-emerald-900 to-slate-900 p-4">
        <Card className="w-full max-w-md">
          <h1 className="text-xl font-semibold text-slate-900 dark:text-white">Listo</h1>
          <p className="text-sm text-slate-600 dark:text-slate-300 mt-2">
            Ya podés entrar a webmail (Roundcube) con <strong className="break-all">{email}</strong> y
            la contraseña que acabás de elegir. Escribí el correo <strong>exactamente</strong> como figura
            arriba (mismo dominio: .com, .co, etc.).
          </p>
          <p className="text-xs text-slate-500 mt-3">Cerrá esta pestaña o abrí webmail con el enlace de tu org.</p>
        </Card>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-indigo-900 to-slate-900 p-4">
      <Card className="w-full max-w-md">
        <h1 className="text-xl font-semibold text-slate-900 dark:text-white">Asignar contraseña de webmail</h1>
        {email && (
          <p className="text-sm text-slate-600 dark:text-slate-300 mt-2 break-all">
            Cuenta: <strong>{email}</strong>
          </p>
        )}
        {expiresAt && (
          <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">
            Caduca: {new Date(expiresAt).toLocaleString()}
          </p>
        )}
        <form onSubmit={onSubmit} className="mt-4 space-y-3">
          {formError && <Alert color="failure">{formError}</Alert>}
          <div>
            <Label htmlFor="p1" value="Nueva contraseña" />
            <div className="relative mt-1">
              <TextInput
                id="p1"
                type={show ? 'text' : 'password'}
                value={pw}
                onChange={(e) => setPw(e.target.value)}
                required
                minLength={10}
                autoComplete="new-password"
              />
              <button
                type="button"
                className="absolute end-2 top-1/2 -translate-y-1/2 p-1 text-slate-500"
                onClick={() => setShow((s) => !s)}
                tabIndex={-1}
                aria-label={show ? 'Ocultar' : 'Mostrar'}
              >
                {show ? <HiEyeOff className="h-5 w-5" /> : <HiEye className="h-5 w-5" />}
              </button>
            </div>
            <p className="text-xs text-slate-500 mt-1">Mínimo 10 caracteres. Es la clave IMAP (Roundcube / Dovecot).</p>
          </div>
          <div>
            <Label htmlFor="p2" value="Repetir contraseña" />
            <TextInput
              id="p2"
              type={show ? 'text' : 'password'}
              value={pw2}
              onChange={(e) => setPw2(e.target.value)}
              required
              minLength={10}
            />
          </div>
          <Button type="submit" className="w-full" disabled={submitting}>
            {submitting ? 'Guardando…' : 'Guardar y activar IMAP'}
          </Button>
        </form>
      </Card>
    </div>
  )
}
