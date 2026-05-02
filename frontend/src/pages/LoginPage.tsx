import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { HiEye, HiEyeOff } from 'react-icons/hi'
import { Alert, Button, Card, Label, TextInput } from 'flowbite-react'
import toast from 'react-hot-toast'
import api from '../api/client'
import { useBranding } from '../api/hooks'
import { useAuthStore } from '../stores/auth'
import { brandingInitials, mergeBranding, type TokenPair } from '../api/types'
import { BrandingFooterCredit } from '../components/BrandingFooterCredit'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [mfa, setMfa] = useState('')
  const [needMfa, setNeedMfa] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showPassword, setShowPassword] = useState(false)
  const [logoFailed, setLogoFailed] = useState(false)
  const setTokens = useAuthStore((s) => s.setTokens)
  const navigate = useNavigate()
  const { data: brandingRaw } = useBranding()
  const b = mergeBranding(brandingRaw)

  useEffect(() => {
    document.title = `Iniciar sesión · ${b.app_name}`
  }, [b.app_name])

  useEffect(() => {
    setLogoFailed(false)
  }, [b.logo_url])

  const showLogoImg = Boolean(b.logo_url && !logoFailed)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const resp = await api.post<TokenPair>('/auth/login', {
        email,
        password,
        mfa_code: needMfa ? mfa : undefined,
      })
      setTokens(resp.data.access_token, resp.data.refresh_token, resp.data.expires_in)
      toast.success('Sesión iniciada')
      navigate('/dashboard', { replace: true })
    } catch (err: any) {
      const raw = err?.response?.data?.detail
      const detail = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : null
      const code = detail?.error as string | undefined
      if (code === 'mfa_required') {
        setNeedMfa(true)
        setError('Ingresá el código MFA de 6 dígitos y volvé a iniciar sesión.')
      } else if (code === 'account_locked') {
        setError(`Cuenta bloqueada. Reintenta en ${detail.retry_after_seconds}s.`)
      } else if (code === 'account_suspended') {
        setError('Tu cuenta está suspendida. Contactá al administrador.')
      } else if (code === 'invalid_mfa_code') {
        setError('Código MFA incorrecto.')
      } else if (err?.response?.status === 401 && code === 'invalid_credentials') {
        setError(
          'Correo o contraseña incorrectos. Si acabás de cambiar la clave por SSH, probá escribir la contraseña a mano (el autocompletado a veces guarda la anterior).',
        )
      } else if (err?.response?.status && err.response.status >= 500) {
        setError('Error en el servidor. Revisá que el contenedor app esté en marcha y el .env tenga SECRET_KEY, FERNET_KEY y acceso a Postgres/Redis (sin tocar, solo que existan y coincidan con el despliegue).')
      } else if (!err?.response) {
        setError('Sin conexión con el servidor o timeout. Revisá la URL y Nginx/SSL.')
      } else {
        setError('No se pudo iniciar sesión. Revisá correo y contraseña.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      className="min-h-screen flex flex-col"
      style={{
        background: `linear-gradient(to bottom right, ${b.primary_color}, ${b.accent_color})`,
      }}
    >
      <div className="flex flex-1 items-center justify-center p-4">
        <Card className="w-full max-w-md">
        <div className="text-center">
          {showLogoImg ? (
            <img
              src={b.logo_url}
              alt=""
              className="mx-auto h-12 w-auto max-w-[220px] object-contain"
              onError={() => setLogoFailed(true)}
            />
          ) : (
            <div
              className="mx-auto h-12 w-12 rounded-lg flex items-center justify-center text-white font-bold text-sm"
              style={{ backgroundColor: b.primary_color }}
            >
              {brandingInitials(b.app_name)}
            </div>
          )}
          <h1 className="mt-3 text-2xl font-semibold text-slate-800 dark:text-slate-100">{b.app_name}</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">Orquestador de backups Google Workspace</p>
        </div>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <Label htmlFor="email" value="Correo" />
            <TextInput
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="password" value="Contraseña" />
            <div className="relative">
              <TextInput
                id="password"
                type={showPassword ? 'text' : 'password'}
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="pr-11"
              />
              <button
                type="button"
                className="absolute end-2 top-1/2 -translate-y-1/2 rounded p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-800 dark:hover:bg-slate-800 dark:hover:text-slate-200"
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'}
              >
                {showPassword ? <HiEyeOff className="h-5 w-5" /> : <HiEye className="h-5 w-5" />}
              </button>
            </div>
          </div>
          {needMfa && (
            <div>
              <Label htmlFor="mfa" value="Código MFA (6 dígitos)" />
              <TextInput
                id="mfa"
                inputMode="numeric"
                maxLength={6}
                required
                value={mfa}
                onChange={(e) => setMfa(e.target.value)}
              />
            </div>
          )}
          {error && <Alert color="failure">{error}</Alert>}
          <Button
            type="submit"
            isProcessing={loading}
            className="w-full text-white"
            style={{ backgroundColor: b.primary_color }}
          >
            Iniciar sesión
          </Button>
        </form>
        </Card>
      </div>
      <footer className="shrink-0 py-3 px-4 text-center">
        <BrandingFooterCredit
          brand={b}
          className="m-0 text-xs text-white/90"
          linkClassName="font-medium underline decoration-white/60 underline-offset-2 hover:text-white"
        />
      </footer>
    </div>
  )
}
