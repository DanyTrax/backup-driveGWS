import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Alert, Button, Card, Label, TextInput } from 'flowbite-react'
import toast from 'react-hot-toast'
import api from '../api/client'
import { useAuthStore } from '../stores/auth'
import type { TokenPair } from '../api/types'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [mfa, setMfa] = useState('')
  const [needMfa, setNeedMfa] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const setTokens = useAuthStore((s) => s.setTokens)
  const navigate = useNavigate()

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
      const detail = err?.response?.data?.detail
      if (detail?.error === 'mfa_required') {
        setNeedMfa(true)
        setError('Se requiere el código MFA')
      } else if (detail?.error === 'account_locked') {
        setError(`Cuenta bloqueada. Reintenta en ${detail.retry_after_seconds}s.`)
      } else {
        setError('Credenciales inválidas')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-600 to-sky-500 p-4">
      <Card className="w-full max-w-md">
        <div className="text-center">
          <div className="mx-auto h-12 w-12 rounded-lg bg-blue-600 flex items-center justify-center text-white font-bold">
            MSA
          </div>
          <h1 className="mt-3 text-2xl font-semibold text-slate-800">Backup Commander</h1>
          <p className="text-sm text-slate-500">Orquestador de backups Google Workspace</p>
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
            <TextInput
              id="password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
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
          <Button type="submit" isProcessing={loading} className="w-full">
            Iniciar sesión
          </Button>
        </form>
      </Card>
    </div>
  )
}
