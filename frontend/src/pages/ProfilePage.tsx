import { useState } from 'react'
import { Alert, Button, Card, Label, TextInput } from 'flowbite-react'
import toast from 'react-hot-toast'
import api from '../api/client'
import { useProfile } from '../api/hooks'

export default function ProfilePage() {
  const { data: profile } = useProfile()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function changePassword(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    try {
      await api.post('/auth/password/change', {
        current_password: current,
        new_password: next,
      })
      toast.success('Contraseña actualizada')
      setCurrent('')
      setNext('')
    } catch {
      setError('No se pudo actualizar la contraseña')
    }
  }

  return (
    <div className="space-y-6 max-w-xl">
      <div>
        <h1 className="text-2xl font-semibold">Perfil</h1>
      </div>
      {profile && (
        <Card>
          <div>
            <div className="text-sm text-slate-500">Correo</div>
            <div className="font-medium">{profile.email}</div>
          </div>
          <div>
            <div className="text-sm text-slate-500">Rol</div>
            <div className="font-medium">{profile.role_code}</div>
          </div>
          <div>
            <div className="text-sm text-slate-500">MFA</div>
            <div className="font-medium">{profile.mfa_enabled ? 'Activo' : 'Inactivo'}</div>
          </div>
        </Card>
      )}
      <Card>
        <h2 className="font-semibold">Cambiar contraseña</h2>
        <form className="space-y-3" onSubmit={changePassword}>
          <div>
            <Label value="Contraseña actual" />
            <TextInput
              type="password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              required
            />
          </div>
          <div>
            <Label value="Nueva contraseña (mín. 12)" />
            <TextInput
              type="password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
              required
              minLength={12}
            />
          </div>
          {error && <Alert color="failure">{error}</Alert>}
          <Button type="submit">Actualizar</Button>
        </form>
      </Card>
    </div>
  )
}
