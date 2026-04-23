import { Card } from 'flowbite-react'
import { Link } from 'react-router-dom'

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Configuración</h1>
        <p className="text-slate-500">Integraciones, branding y operación</p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <h2 className="font-semibold">Asistente inicial</h2>
          <p className="text-sm text-slate-500">
            Si necesitas rehacer la configuración de Google Workspace puedes volver al wizard.
          </p>
          <Link className="text-blue-600 font-medium" to="/setup">
            Abrir asistente
          </Link>
        </Card>
        <Card>
          <h2 className="font-semibold">Notificaciones</h2>
          <p className="text-sm text-slate-500">
            Conecta Telegram, Discord y Gmail. Define matrices por categoría.
          </p>
        </Card>
        <Card>
          <h2 className="font-semibold">Branding</h2>
          <p className="text-sm text-slate-500">
            Cambia logo, colores y nombre visible de la plataforma.
          </p>
        </Card>
        <Card>
          <h2 className="font-semibold">Git Refresh</h2>
          <p className="text-sm text-slate-500">
            Despliega la última versión de la plataforma desde el repositorio.
          </p>
        </Card>
      </div>
    </div>
  )
}
