import { Button, Card } from 'flowbite-react'
import { HiOutlineCloudUpload, HiOutlineShieldCheck, HiOutlineMail } from 'react-icons/hi'
import { useEffect, useState } from 'react'

interface HealthData {
  status: string
  app: string
  version: string
  env: string
  time: string
}

export default function LandingPage() {
  const [health, setHealth] = useState<HealthData | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/health')
      .then(r => (r.ok ? r.json() : Promise.reject(r.statusText)))
      .then(setHealth)
      .catch(err => setError(String(err)))
  }, [])

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="max-w-4xl w-full space-y-6">
        <div className="text-center space-y-3">
          <h1 className="text-4xl font-bold text-slate-900 dark:text-white">
            MSA Backup Commander
          </h1>
          <p className="text-lg text-slate-600 dark:text-slate-300">
            Orquestador empresarial de backups Google Workspace — Drive, Gmail y webmail integrado.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card>
            <HiOutlineCloudUpload className="w-8 h-8 text-brand-600" />
            <h3 className="text-xl font-semibold">Drive + Gmail</h3>
            <p className="text-sm text-slate-600 dark:text-slate-400">
              Respaldo total e incremental con rclone y GYB.
            </p>
          </Card>
          <Card>
            <HiOutlineMail className="w-8 h-8 text-brand-600" />
            <h3 className="text-xl font-semibold">Webmail integrado</h3>
            <p className="text-sm text-slate-600 dark:text-slate-400">
              Roundcube + Dovecot con SSO para el admin y magic link para clientes.
            </p>
          </Card>
          <Card>
            <HiOutlineShieldCheck className="w-8 h-8 text-brand-600" />
            <h3 className="text-xl font-semibold">Seguridad</h3>
            <p className="text-sm text-slate-600 dark:text-slate-400">
              RBAC granular, MFA, lockout exponencial, cifrado en reposo.
            </p>
          </Card>
        </div>

        <Card>
          <h3 className="text-lg font-semibold mb-3">Estado del backend</h3>
          {health && (
            <dl className="grid grid-cols-2 gap-2 text-sm">
              <dt className="text-slate-500">Status:</dt>
              <dd className="font-mono">{health.status}</dd>
              <dt className="text-slate-500">Versión:</dt>
              <dd className="font-mono">{health.version}</dd>
              <dt className="text-slate-500">Entorno:</dt>
              <dd className="font-mono">{health.env}</dd>
              <dt className="text-slate-500">Hora servidor:</dt>
              <dd className="font-mono">{health.time}</dd>
            </dl>
          )}
          {error && (
            <p className="text-red-600 text-sm">Backend sin responder: {error}</p>
          )}
          {!health && !error && <p className="text-slate-500">Consultando /api/health...</p>}
        </Card>

        <div className="flex justify-center gap-3">
          <Button color="blue" href="/api/docs">Ver API docs</Button>
          <Button color="light" href="https://github.com/DanyTrax/backup-driveGWS">GitHub</Button>
        </div>
      </div>
    </div>
  )
}
