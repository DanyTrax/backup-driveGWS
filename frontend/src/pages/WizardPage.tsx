import { useState } from 'react'
import { Button, Card, Label, Textarea, TextInput } from 'flowbite-react'
import toast from 'react-hot-toast'
import { useNavigate } from 'react-router-dom'
import api from '../api/client'
import { useSetupState } from '../api/hooks'

export default function WizardPage() {
  const { data: state, refetch } = useSetupState()
  const [sa, setSa] = useState('')
  const [admin, setAdmin] = useState('')
  const [drive, setDrive] = useState('')
  const [root, setRoot] = useState('')
  const navigate = useNavigate()

  async function submitSa() {
    try {
      await api.post('/setup/service-account', {
        service_account_json: sa,
        delegated_admin_email: admin,
      })
      toast.success('Service Account registrada')
      refetch()
    } catch {
      toast.error('JSON inválido o correo inválido')
    }
  }

  async function checkDelegation() {
    try {
      const resp = await api.post('/setup/check-directory')
      if (resp.data.ok) toast.success('DWD operativo')
      else toast.error(`Error: ${resp.data.error}`)
      refetch()
    } catch {
      toast.error('Fallo comprobando delegación')
    }
  }

  async function submitDrive() {
    try {
      const resp = await api.post('/setup/vault/shared-drive', { shared_drive_id: drive })
      if (resp.data.ok) toast.success(`Shared Drive: ${resp.data.drive?.name}`)
      refetch()
    } catch {
      toast.error('No se pudo validar Shared Drive')
    }
  }

  async function submitRoot() {
    try {
      await api.post('/setup/vault/root-folder', { root_folder_id: root })
      await api.post('/setup/vault/create-structure')
      toast.success('Estructura del vault creada')
      refetch()
    } catch {
      toast.error('No se pudo crear la estructura')
    }
  }

  async function complete() {
    await api.post('/setup/complete')
    toast.success('Setup marcado como completado')
    navigate('/dashboard')
  }

  return (
    <div className="space-y-6 max-w-3xl mx-auto">
      <div>
        <h1 className="text-2xl font-semibold">Asistente de configuración</h1>
        <p className="text-slate-500">
          Sigue los pasos para conectar Google Workspace y el vault de 38 TB
        </p>
      </div>

      <Card>
        <h2 className="font-semibold mb-2">1. Service Account con DWD</h2>
        <p className="text-sm text-slate-500 mb-3">
          Crea un Service Account en GCP, descarga el JSON y autoriza el Client ID en Admin → Security
          → API Controls → Domain-wide Delegation con los scopes indicados.
        </p>
        <Label value="JSON del Service Account" />
        <Textarea
          rows={6}
          value={sa}
          onChange={(e) => setSa(e.target.value)}
          placeholder='{"type":"service_account", ...}'
        />
        <div className="mt-3">
          <Label value="Correo del super-admin a impersonar" />
          <TextInput value={admin} onChange={(e) => setAdmin(e.target.value)} placeholder="admin@dominio.com" />
        </div>
        <div className="text-right mt-3">
          <Button onClick={submitSa}>Guardar credenciales</Button>
        </div>
        {state?.required_scopes && (
          <div className="mt-3 text-xs text-slate-500">
            Scopes requeridos: {state.required_scopes.join(', ')}
          </div>
        )}
      </Card>

      <Card>
        <h2 className="font-semibold mb-2">2. Verificar delegación</h2>
        <Button onClick={checkDelegation}>Probar acceso al directorio</Button>
      </Card>

      <Card>
        <h2 className="font-semibold mb-2">3. Shared Drive del vault</h2>
        <Label value="ID del Shared Drive" />
        <TextInput value={drive} onChange={(e) => setDrive(e.target.value)} />
        <div className="text-right mt-3">
          <Button onClick={submitDrive}>Validar Shared Drive</Button>
        </div>
      </Card>

      <Card>
        <h2 className="font-semibold mb-2">4. Carpeta raíz del vault</h2>
        <Label value="ID de la carpeta raíz dentro del Shared Drive" />
        <TextInput value={root} onChange={(e) => setRoot(e.target.value)} />
        <div className="text-right mt-3">
          <Button onClick={submitRoot}>Guardar y crear estructura</Button>
        </div>
      </Card>

      <Card>
        <h2 className="font-semibold mb-2">5. Finalizar</h2>
        <p className="text-sm text-slate-500 mb-3">
          Estado actual: <strong>{state?.current_step}</strong>
        </p>
        <Button color="success" onClick={complete}>
          Marcar setup como completado
        </Button>
      </Card>
    </div>
  )
}
