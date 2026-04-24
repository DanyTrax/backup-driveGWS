import { Button, Card } from 'flowbite-react'
import toast from 'react-hot-toast'
import { HiRefresh } from 'react-icons/hi'
import { Link } from 'react-router-dom'
import { useGitRefresh, usePlatformBackupRun, useProfile } from '../api/hooks'

export default function SettingsPage() {
  const { data: profile } = useProfile()
  const gitRefresh = useGitRefresh()
  const platformBackup = usePlatformBackupRun()
  const perms = new Set(profile?.permissions ?? [])
  const canGitRefresh = perms.has('platform.refresh')
  const canPlatformBackup = perms.has('platform.backup')

  async function onGitRefresh() {
    try {
      const r = await gitRefresh.mutateAsync()
      if (r.error === 'not_a_git_repository' && r.hint) {
        toast.error(r.hint, { duration: 14_000 })
        return
      }
      if (r.ok) {
        const short = r.head ? `${r.head.slice(0, 7)}` : '—'
        toast.success(`Repositorio actualizado (fetch, checkout, reset). HEAD ${short}`)
      } else {
        const last = r.steps?.filter((s) => s.rc !== 0).pop() ?? r.steps?.[r.steps.length - 1]
        const hint = [last?.stderr, last?.stdout].filter(Boolean).join('\n').trim()
        toast.error(hint ? `Git refresh falló:\n${hint.slice(0, 500)}` : 'Git refresh falló (revisá logs del contenedor).')
      }
    } catch (err: unknown) {
      const st = (err as { response?: { status?: number } })?.response?.status
      if (st === 403) {
        toast.error('No tenés permiso para Git refresh (hace falta platform.refresh).')
      } else {
        toast.error('No se pudo ejecutar Git refresh.')
      }
    }
  }

  async function onPlatformBackup() {
    try {
      const r = await platformBackup.mutateAsync()
      if (r.ok) {
        toast.success(`Backup de plataforma subido: ${r.filename ?? 'archivo .age'}`)
      } else {
        const code = r.error ?? 'error_desconocido'
        const reason = (r as { reason?: string }).reason ?? ''
        const msg =
          code === 'platform_backup_exception' && reason
            ? `Backup de plataforma: ${reason.slice(0, 400)}`
            : code === 'age_recipient_not_configured'
              ? 'Falta configurar el destinatario age (PLATFORM_BACKUP_AGE_RECIPIENT) en el servidor.'
              : code === 'vault_root_missing'
                ? 'Falta vault de Drive configurado.'
                : reason
                  ? `${code}: ${reason.slice(0, 300)}`
                  : `No se pudo generar el backup (${code}).`
        toast.error(msg)
      }
    } catch (err: unknown) {
      const st = (err as { response?: { status?: number } })?.response?.status
      if (st === 403) {
        toast.error('No tenés permiso para backup de plataforma (platform.backup).')
      } else {
        toast.error('No se pudo ejecutar el backup de plataforma.')
      }
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Configuración</h1>
        <p className="text-slate-500">Integraciones, branding y operación</p>
      </div>
      <p className="text-xs text-slate-400">
        Compilación de esta interfaz:{' '}
        <code className="bg-slate-100 dark:bg-slate-800 px-1 rounded">{import.meta.env.VITE_UI_BUILD_ID}</code>
        . Si los mensajes de error no coinciden con lo esperado o ves textos “viejos”, recargá sin caché
        (Ctrl+Shift+R o Cmd+Shift+R) o reconstruí la imagen Docker del frontend.
      </p>
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
          <h2 className="font-semibold mb-2">Git y respaldo de plataforma</h2>
          <p className="text-sm text-slate-500 mb-4">
            <strong>En VPS con imagen Docker</strong> el código en <code className="text-xs">/app</code> no trae carpeta{' '}
            <code className="text-xs">.git</code>: ahí tenés que actualizar con{' '}
            <code className="text-xs">git pull</code> en el host (<code className="text-xs">/opt/stacks/backup-stack</code>) y{' '}
            <code className="text-xs">docker compose up -d --build</code> desde <code className="text-xs">docker/</code>.
            El botón solo sirve si montás un repo con <code className="text-xs">.git</code> y configurás{' '}
            <code className="text-xs">GIT_WORKING_TREE</code> en <code className="text-xs">.env</code>.
          </p>
          <div className="flex flex-wrap gap-2">
            {canGitRefresh ? (
              <Button
                color="blue"
                onClick={() => void onGitRefresh()}
                disabled={gitRefresh.isPending}
                isProcessing={gitRefresh.isPending}
              >
                <HiRefresh className="h-4 w-4 mr-2" />
                Actualizar repositorio (Git refresh)
              </Button>
            ) : (
              <p className="text-sm text-amber-700 dark:text-amber-400">
                Tu rol no incluye permiso <code className="text-xs">platform.refresh</code>.
              </p>
            )}
            {canPlatformBackup ? (
              <Button
                color="light"
                onClick={() => void onPlatformBackup()}
                disabled={platformBackup.isPending}
                isProcessing={platformBackup.isPending}
              >
                Backup cifrado de plataforma
              </Button>
            ) : null}
          </div>
        </Card>
      </div>
    </div>
  )
}
