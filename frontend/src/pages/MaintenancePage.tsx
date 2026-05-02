import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Label,
  Select,
  Spinner,
  TextInput,
} from 'flowbite-react'
import toast from 'react-hot-toast'
import { HiServer, HiTrash } from 'react-icons/hi'
import {
  useDockerPruneRun,
  useHostOpsConfig,
  useHostOpsScheduleSave,
  useProfile,
  useStackDeployRun,
} from '../api/hooks'

const DOW_OPTS: { v: string; label: string }[] = [
  { v: '', label: 'Todos los días' },
  { v: '0', label: 'Domingo' },
  { v: '1', label: 'Lunes' },
  { v: '2', label: 'Martes' },
  { v: '3', label: 'Miércoles' },
  { v: '4', label: 'Jueves' },
  { v: '5', label: 'Viernes' },
  { v: '6', label: 'Sábado' },
]

export default function MaintenancePage() {
  const { data: profile } = useProfile()
  const perms = useMemo(() => new Set(profile?.permissions ?? []), [profile?.permissions])
  const canDocker = perms.has('platform.host_docker')
  const canDeploy = perms.has('platform.stack_deploy')

  const cfgQ = useHostOpsConfig()
  const pruneMut = useDockerPruneRun()
  const schedMut = useHostOpsScheduleSave()
  const deployMut = useStackDeployRun()

  const s = cfgQ.data?.schedule
  const [schedEnabled, setSchedEnabled] = useState(false)
  const [schedPreset, setSchedPreset] = useState<'light' | 'deep'>('deep')
  const [schedHour, setSchedHour] = useState(4)
  const [schedMinute, setSchedMinute] = useState(10)
  const [schedDow, setSchedDow] = useState('')

  useEffect(() => {
    if (!s) return
    setSchedEnabled(s.enabled)
    setSchedPreset(s.preset === 'light' ? 'light' : 'deep')
    setSchedHour(s.hour)
    setSchedMinute(s.minute)
    setSchedDow(s.dow == null ? '' : String(s.dow))
  }, [s])

  if (!canDocker && !canDeploy) {
    return (
      <Alert color="failure">
        No tenés permiso para esta sección (solo super administradores con permisos de mantenimiento).
      </Alert>
    )
  }

  async function saveSchedule() {
    try {
      await schedMut.mutateAsync({
        enabled: schedEnabled,
        preset: schedPreset,
        hour: schedHour,
        minute: schedMinute,
        dow: schedDow === '' ? null : Number(schedDow),
      })
      toast.success('Programación guardada')
    } catch {
      toast.error('No se pudo guardar')
    }
  }

  const readyDocker = cfgQ.data?.docker_control_enabled && cfgQ.data?.docker_socket_present
  const readyDeploy =
    cfgQ.data?.stack_deploy_enabled &&
    cfgQ.data?.docker_socket_present &&
    cfgQ.data?.stack_path_configured

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-xl font-semibold text-slate-900 dark:text-white flex items-center gap-2">
          <HiServer className="h-6 w-6" /> Mantenimiento del host
        </h1>
        <p className="text-sm text-slate-600 dark:text-slate-400 mt-1">
          Limpieza de imágenes Docker (containerd) y, si lo configurás en el servidor, actualización de la pila con{' '}
          <code className="text-xs">docker compose</code>. Requiere variables <code className="text-xs">HOST_*</code> en{' '}
          <code className="text-xs">.env</code> y montajes en el servicio <code className="text-xs">app</code>.
        </p>
      </div>

      {cfgQ.isLoading ? (
        <Spinner />
      ) : cfgQ.isError ? (
        <Alert color="failure">No se pudo cargar la configuración</Alert>
      ) : (
        <>
          <Alert color="info">
            <span className="font-medium">Estado</span>
            <ul className="mt-2 text-sm list-disc pl-5 space-y-1">
              <li>
                Control Docker (API):{' '}
                <strong>{cfgQ.data!.docker_control_enabled ? 'habilitado en .env' : 'desactivado'}</strong> — socket{' '}
                {cfgQ.data!.docker_socket_present ? 'visible' : 'no encontrado'}.
              </li>
              <li>
                Despliegue: <strong>{cfgQ.data!.stack_deploy_enabled ? 'habilitado' : 'desactivado'}</strong> — ruta stack{' '}
                {cfgQ.data!.stack_path_configured ? `OK (${cfgQ.data!.compose_dir ?? '—'})` : 'no configurada'}.
              </li>
            </ul>
          </Alert>

          {canDocker ? (
            <Card>
              <div className="flex items-center gap-2 mb-3">
                <HiTrash className="h-5 w-5 text-slate-600" />
                <h2 className="text-lg font-medium">Limpieza Docker</h2>
              </div>
              <p className="text-sm text-slate-600 dark:text-slate-400 mb-4">
                <strong>Ligera:</strong> <code className="text-xs">docker system prune -f</code>. <strong>Profunda:</strong>{' '}
                además <code className="text-xs">image prune -a</code> y <code className="text-xs">builder prune</code>{' '}
                (libera lo acumulado en containerd). No borra volúmenes nombrados en uso.
              </p>
              {!readyDocker ? (
                <Alert color="warning">
                  Activá <code className="text-xs">HOST_DOCKER_CONTROL_ENABLED=true</code>, montá{' '}
                  <code className="text-xs">docker.sock</code> en <code className="text-xs">app</code> y asigná el GID del
                  grupo <code className="text-xs">docker</code> del host (<code className="text-xs">group_add</code>).
                </Alert>
              ) : (
                <div className="flex flex-wrap gap-2">
                  <Button
                    color="light"
                    disabled={pruneMut.isPending}
                    onClick={() =>
                      void pruneMut.mutateAsync('light').then((r) =>
                        (r as { ok?: boolean }).ok ? toast.success('Limpieza ligera terminada') : toast.error('Falló'),
                      )
                    }
                  >
                    Limpiar (ligera)
                  </Button>
                  <Button
                    color="warning"
                    disabled={pruneMut.isPending}
                    onClick={() =>
                      void pruneMut.mutateAsync('deep').then((r) =>
                        (r as { ok?: boolean }).ok ? toast.success('Limpieza profunda terminada') : toast.error('Falló'),
                      )
                    }
                  >
                    Limpiar (profunda)
                  </Button>
                </div>
              )}

              <hr className="my-6 border-slate-200 dark:border-slate-700" />

              <h3 className="text-sm font-semibold mb-3">Programación</h3>
              <p className="text-xs text-slate-500 mb-3">
                Hora en la zona <code className="text-[10px]">TZ</code> del backend. Beat revisa cada 5 minutos; como mucho
                una ejecución exitosa por día calendario.
              </p>
              <div className="flex flex-wrap items-end gap-4">
                <div className="flex items-center gap-2">
                  <Checkbox id="sch-en" checked={schedEnabled} onChange={(e) => setSchedEnabled(e.target.checked)} />
                  <Label htmlFor="sch-en">Activa limpieza programada</Label>
                </div>
                <div>
                  <Label value="Modo" />
                  <Select value={schedPreset} onChange={(e) => setSchedPreset(e.target.value as 'light' | 'deep')}>
                    <option value="light">Ligera</option>
                    <option value="deep">Profunda</option>
                  </Select>
                </div>
                <div>
                  <Label value="Hora (0–23)" />
                  <TextInput
                    type="number"
                    min={0}
                    max={23}
                    value={schedHour}
                    onChange={(e) => setSchedHour(Number(e.target.value))}
                  />
                </div>
                <div>
                  <Label value="Minuto (0–59)" />
                  <TextInput
                    type="number"
                    min={0}
                    max={59}
                    value={schedMinute}
                    onChange={(e) => setSchedMinute(Number(e.target.value))}
                  />
                </div>
                <div className="min-w-[10rem]">
                  <Label value="Día" />
                  <Select value={schedDow} onChange={(e) => setSchedDow(e.target.value)}>
                    {DOW_OPTS.map((o) => (
                      <option key={o.v || 'all'} value={o.v}>
                        {o.label}
                      </option>
                    ))}
                  </Select>
                </div>
                <Button color="light" onClick={() => void saveSchedule()} disabled={schedMut.isPending || !readyDocker}>
                  Guardar programación
                </Button>
              </div>
              {s?.last_run_date ? (
                <p className="text-xs text-slate-500 mt-2">Última ejecución guardada: {s.last_run_date}</p>
              ) : null}
            </Card>
          ) : null}

          {canDeploy ? (
            <Card>
              <h2 className="text-lg font-medium mb-2">Actualizar la pila (compose)</h2>
              <p className="text-sm text-slate-600 dark:text-slate-400 mb-4">
                <strong>Completo</strong>: <code className="text-xs">git pull --ff-only</code> y{' '}
                <code className="text-xs">docker compose build &amp;&amp; up -d</code>. El resto son variantes sin tocar
                Postgres/Redis salvo que el compose las recree.
              </p>
              {!readyDeploy ? (
                <Alert color="warning">
                  Activá <code className="text-xs">HOST_STACK_DEPLOY_ENABLED=true</code>, montá el repo en la{' '}
                  <strong>misma ruta</strong> en host y contenedor (p. ej.{' '}
                  <code className="text-xs">/opt/stacks/backup-stack:/opt/stacks/backup-stack</code>) y definí{' '}
                  <code className="text-xs">HOST_STACK_MOUNT_PATH=/opt/stacks/backup-stack</code>.
                </Alert>
              ) : (
                <div className="flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    color="light"
                    disabled={deployMut.isPending}
                    onClick={() =>
                      void deployMut.mutateAsync('frontend').then((r) =>
                        (r as { ok?: boolean }).ok ? toast.success('Listo') : toast.error('Falló'),
                      )
                    }
                  >
                    Solo front (build app + up app)
                  </Button>
                  <Button
                    size="sm"
                    color="light"
                    disabled={deployMut.isPending}
                    onClick={() =>
                      void deployMut.mutateAsync('frontend_backend').then((r) =>
                        (r as { ok?: boolean }).ok ? toast.success('Listo') : toast.error('Falló'),
                      )
                    }
                  >
                    Front + worker/beat
                  </Button>
                  <Button
                    size="sm"
                    color="gray"
                    disabled={deployMut.isPending}
                    onClick={() =>
                      void deployMut.mutateAsync('rebuild_app').then((r) =>
                        (r as { ok?: boolean }).ok ? toast.success('Build app OK') : toast.error('Falló'),
                      )
                    }
                  >
                    Solo rebuild imagen app
                  </Button>
                  <Button
                    size="sm"
                    color="failure"
                    disabled={deployMut.isPending}
                    onClick={() => {
                      if (!window.confirm('¿Git pull + build + up de toda la pila?')) return
                      void deployMut.mutateAsync('full').then((r) =>
                        (r as { ok?: boolean }).ok ? toast.success('Despliegue completo') : toast.error('Falló'),
                      )
                    }}
                  >
                    Completo (git pull + compose)
                  </Button>
                </div>
              )}
            </Card>
          ) : null}
        </>
      )}
    </div>
  )
}
