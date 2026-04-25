import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { HiEye, HiEyeOff } from 'react-icons/hi'
import { Alert, Button, Card, Label, Spinner, TextInput } from 'flowbite-react'
import toast from 'react-hot-toast'
import api from '../api/client'
type Status = 'loading' | 'ready' | 'invalid' | 'done'

export default function WebmailAssignPasswordPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token') ?? ''
  const [status, setStatus] = useState<Status>('loading')
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
      return
    }
    setStatus('loading')
    try {
      const resp = await api.get<{
        email: string
        expires_at: string
      }>('/webmail/password-setup/status', { params: { token } })
      setEmail(resp.data.email)
      setExpiresAt(resp.data.expires_at)
      setStatus('ready')
    } catch {
      setStatus('invalid')
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
      await api.post('/webmail/password-setup/complete', { token, new_password: pw })
      setStatus('done')
      toast.success('Contraseña de webmail / IMAP guardada')
    } catch (err) {
      const ax = err as { response?: { data?: { detail?: unknown } } }
      const d = ax.response?.data?.detail
      const code = typeof d === 'string' ? d : (d as { error?: string } | undefined)?.error
      if (d === 'token_expired' || d === 'invalid_or_expired_token' || d === 'invalid_token') {
        setFormError('El enlace expiró o ya no es válido. Pedí uno nuevo a tu administrador.')
        return
      }
      if (d === 'token_already_used') {
        setFormError('Este enlace ya se usó. Si ya fijaste la clave, entrá a webmail con correo y contraseña.')
        return
      }
      if (d === 'password_too_short' || code === 'password_too_short') {
        setFormError('La contraseña es demasiado corta (mínimo 10 caracteres).')
        return
      }
      if (d === 'rate_limited' || (typeof d === 'object' && d && 'error' in d && (d as { error: string }).error === 'rate_limited')) {
        setFormError('Demasiados intentos. Reintentá en un rato.')
        return
      }
      setFormError('No se pudo guardar la contraseña. Reintentá o pedí un enlace nuevo.')
    } finally {
      setSubmitting(false)
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
          <h1 className="text-xl font-semibold text-slate-900 dark:text-white">Enlace no válido</h1>
          <p className="text-sm text-slate-600 dark:text-slate-300 mt-2">
            El enlace venció, ya se usó o no existe. Contactá a tu administrador para generar un enlace
            de asignación de contraseña (hasta 24 h).
          </p>
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
            la contraseña que acabás de elegir, o desde el panel con esas credenciales.
          </p>
          <p className="text-xs text-slate-500 mt-3">Cerrá esta pestaña o abrí webmail en el enlace del administrador.</p>
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
