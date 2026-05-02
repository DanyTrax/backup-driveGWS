import { useEffect, useMemo, useRef, useState } from 'react'
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
  useStackDeployJob,
  useStackDeployRun,
} from '../api/hooks'
import type { StackDeployMode, StackDeployResult } from '../api/types'

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

const STACK_MODE_LABEL: Record<StackDeployMode, string> = {
  frontend: 'Solo front (build app + up app)',
  frontend_backend: 'Front + worker/beat',
  rebuild_app: 'Solo rebuild imagen app',
  full: 'Completo (git pull + compose)',
}

type StackDeployTerminalState =
  | { kind: 'idle' }
  | { kind: 'running'; mode: StackDeployMode; logsTail?: string }
  | { kind: 'done'; result: StackDeployResult }
  | { kind: 'error'; message: string }

export default function MaintenancePage() {
  const { data: profile } = useProfile()
  const perms = useMemo(() => new Set(profile?.permissions ?? []), [profile?.permissions])
  const canDocker = perms.has('platform.host_docker')
  const canDeploy = perms.has('platform.stack_deploy')

  const cfgQ = useHostOpsConfig()
  const pruneMut = useDockerPruneRun()
  const schedMut = useHostOpsScheduleSave()
  const deployMut = useStackDeployRun()
  const [deployJobId, setDeployJobId] = useState<string | null>(null)
  const jobQ = useStackDeployJob(deployJobId)

  const stackTermScrollRef = useRef<HTMLDivElement>(null)
  const [stackTerm, setStackTerm] = useState<StackDeployTerminalState>({ kind: 'idle' })

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

  useEffect(() => {
    const el = stackTermScrollRef.current
    if (!el) return
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [stackTerm, jobQ.data?.logs_tail])

  useEffect(() => {
    const d = jobQ.data
    if (!d || deployJobId === null) return

    if (d.phase === 'running') {
      if (d.logs_tail) {
        setStackTerm((prev) =>
          prev.kind === 'running' ? { ...prev, logsTail: d.logs_tail ?? undefined } : prev,
        )
      }
      return
    }

    if (d.phase === 'unknown') {
      const msg = [d.error, d.stderr_tail].filter(Boolean).join(' — ') || 'No se pudo consultar el trabajo.'
      setStackTerm({ kind: 'error', message: msg })
      toast.error('Error al consultar el despliegue')
      setDeployJobId(null)
      return
    }

    if (d.phase === 'finished') {
      setDeployJobId(null)
      if (d.result) {
        setStackTerm({ kind: 'done', result: d.result })
        const m = d.result.mode
        if (d.result.ok) {
          toast.success(
            m === 'full' ? 'Despliegue completo' : m === 'rebuild_app' ? 'Build app OK' : 'Listo',
          )
        } else {
          toast.error('Falló — revisá la salida abajo')
        }
      } else {
        const fallback =
          d.logs_tail ||
          (d.exit_code !== undefined ? `Proceso terminó con código ${d.exit_code}.` : '') ||
          'No se pudo leer el resultado JSON del contenedor de despliegue (revisá docker logs en el servidor).'
        setStackTerm({ kind: 'error', message: fallback })
        toast.error('Despliegue terminó sin resultado parseable')
      }
    }
  }, [jobQ.data, deployJobId])

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
  const deployBase =
    cfgQ.data?.stack_deploy_enabled &&
    cfgQ.data?.docker_socket_present &&
    cfgQ.data?.stack_path_configured
  const runnerOk = Boolean(cfgQ.data?.runner_image_configured)
  const readyDeploy = Boolean(deployBase && runnerOk)

  const deployBusy = deployMut.isPending || deployJobId !== null

  async function runStackDeploy(mode: StackDeployMode) {
    if (mode === 'full' && !window.confirm('¿Git pull + build + up de toda la pila?')) return
    setDeployJobId(null)
    setStackTerm({ kind: 'running', mode })
    try {
      const start = await deployMut.mutateAsync(mode)
      if (!start.ok || !start.job) {
        const msg = [start.error, start.hint, start.stderr_tail].filter(Boolean).join(' — ')
        setStackTerm({
          kind: 'error',
          message: msg || 'No se pudo iniciar el contenedor de despliegue.',
        })
        toast.error('No se pudo iniciar el despliegue')
        return
      }
      setDeployJobId(start.job)
      toast.success('Despliegue en segundo plano; el panel puede cortarse unos segundos — seguí la salida abajo.')
    } catch {
      setStackTerm({
        kind: 'error',
        message: 'No se pudo contactar al servidor.',
      })
      toast.error('Error de red')
    }
  }

  return (
    <div className="space-y-6 max-w-5xl">
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
                {cfgQ.data!.stack_path_configured ? `OK (${cfgQ.data!.compose_dir ?? '—'})` : 'no configurada'}; imagen
                runner:{' '}
                {cfgQ.data!.runner_image_configured ? (
                  <strong>definida</strong>
                ) : (
                  <strong>falta HOST_STACK_DEPLOY_RUNNER_IMAGE</strong>
                )}
                .
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
                El trabajo corre en un <strong>contenedor aparte</strong> (<code className="text-xs">docker run</code>), así
                el despliegue sigue aunque el panel se reinicie.{' '}
                <strong>Completo</strong>: <code className="text-xs">git pull --ff-only</code> y{' '}
                <code className="text-xs">docker compose build &amp;&amp; up -d</code>.
              </p>
              {!deployBase ? (
                <Alert color="warning">
                  Activá <code className="text-xs">HOST_STACK_DEPLOY_ENABLED=true</code>, montá el repo en la{' '}
                  <strong>misma ruta</strong> en host y contenedor (p. ej.{' '}
                  <code className="text-xs">/opt/stacks/backup-stack:/opt/stacks/backup-stack</code>) y definí{' '}
                  <code className="text-xs">HOST_STACK_MOUNT_PATH=/opt/stacks/backup-stack</code>.
                </Alert>
              ) : !runnerOk ? (
                <Alert color="warning">
                  Definí <code className="text-xs">HOST_STACK_DEPLOY_RUNNER_IMAGE</code> en <code className="text-xs">.env</code>{' '}
                  (misma imagen que el servicio <code className="text-xs">app</code>, p. ej.{' '}
                  <code className="text-xs">ghcr.io/danytrax/backup-drivegws-app:latest</code>). El{' '}
                  <code className="text-xs">docker-compose.yml</code> del repo puede inyectarla en el servicio{' '}
                  <code className="text-xs">app</code>.
                </Alert>
              ) : (
                <>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      size="sm"
                      color="light"
                      disabled={deployBusy}
                      onClick={() => void runStackDeploy('frontend')}
                    >
                      Solo front (build app + up app)
                    </Button>
                    <Button
                      size="sm"
                      color="light"
                      disabled={deployBusy}
                      onClick={() => void runStackDeploy('frontend_backend')}
                    >
                      Front + worker/beat
                    </Button>
                    <Button
                      size="sm"
                      color="gray"
                      disabled={deployBusy}
                      onClick={() => void runStackDeploy('rebuild_app')}
                    >
                      Solo rebuild imagen app
                    </Button>
                    <Button
                      size="sm"
                      color="failure"
                      disabled={deployBusy}
                      onClick={() => void runStackDeploy('full')}
                    >
                      Completo (git pull + compose)
                    </Button>
                  </div>

                  <div className="mt-6 space-y-2">
                    <div className="flex items-center justify-between gap-2">
                      <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-200">
                        Salida del despliegue
                      </h3>
                      <span className="text-[10px] uppercase tracking-wide text-slate-500">simulación de consola</span>
                    </div>
                    <div
                      ref={stackTermScrollRef}
                      className="rounded-lg border border-slate-700 dark:border-slate-600 bg-slate-950 text-slate-100 font-mono text-[11px] leading-relaxed shadow-inner max-h-[min(28rem,55vh)] overflow-y-auto overflow-x-auto"
                    >
                      <div className="sticky top-0 flex items-center gap-2 border-b border-slate-800 bg-slate-900/95 px-3 py-1.5 text-[10px] text-slate-500">
                        <span className="inline-flex gap-1">
                          <span className="h-2 w-2 rounded-full bg-red-500/80" />
                          <span className="h-2 w-2 rounded-full bg-amber-500/80" />
                          <span className="h-2 w-2 rounded-full bg-green-500/80" />
                        </span>
                        <span>host-ops — stack-deploy</span>
                      </div>
                      <div className="p-3 space-y-4">
                        {stackTerm.kind === 'idle' ? (
                          <p className="text-slate-500">
                            El despliegue corre fuera del contenedor del panel; podés recargar la página si se cae la
                            conexión: el resultado se actualiza al terminar. Verás cada comando y el final de{' '}
                            <span className="text-slate-400">stderr</span> (truncado en el servidor).
                          </p>
                        ) : null}

                        {stackTerm.kind === 'running' ? (
                          <div className="space-y-2">
                            <div>
                              <p className="text-amber-400/90 animate-pulse">⟳ Contenedor de despliegue en ejecución…</p>
                              <p className="text-slate-500">
                                Modo: <span className="text-slate-300">{STACK_MODE_LABEL[stackTerm.mode]}</span>
                              </p>
                              <p className="text-slate-600 text-[10px]">
                                Si el panel deja de responder, esperá y recargá; el sondeo sigue cuando vuelva la API.
                              </p>
                            </div>
                            {stackTerm.logsTail ? (
                              <pre className="max-h-56 overflow-y-auto whitespace-pre-wrap break-words rounded bg-black/40 px-2 py-1.5 text-slate-500 text-[10px]">
                                {stackTerm.logsTail}
                              </pre>
                            ) : null}
                          </div>
                        ) : null}

                        {stackTerm.kind === 'error' ? (
                          <p className="text-red-400 font-medium">{stackTerm.message}</p>
                        ) : null}

                        {stackTerm.kind === 'done' ? (
                          <div className="space-y-3">
                            <p
                              className={
                                stackTerm.result.ok
                                  ? 'text-emerald-400 font-medium'
                                  : 'text-red-400 font-medium'
                              }
                            >
                              {stackTerm.result.ok
                                ? '✓ Finalizado correctamente'
                                : `✗ Error: ${stackTerm.result.error ?? 'desconocido'}`}
                            </p>
                            {(stackTerm.result.steps ?? []).length === 0 && stackTerm.result.error ? (
                              <p className="text-slate-500">No hay pasos registrados (falló la comprobación inicial).</p>
                            ) : null}
                            {(stackTerm.result.steps ?? []).map((step, i) => (
                              <div
                                key={`${step.cmd}-${i}`}
                                className="border-l-2 border-slate-700 pl-3 space-y-1"
                              >
                                <div className="text-green-400">
                                  <span className="text-slate-600 select-none mr-2">$</span>
                                  {step.cmd}
                                </div>
                                <div className={step.rc === 0 ? 'text-slate-400' : 'text-red-400'}>
                                  → exit {step.rc}
                                  {step.note ? (
                                    <span className="text-slate-500"> — {step.note}</span>
                                  ) : null}
                                </div>
                                {step.stderr_tail ? (
                                  <pre className="mt-1 max-h-48 overflow-y-auto whitespace-pre-wrap break-words rounded bg-black/40 px-2 py-1.5 text-slate-400 text-[10px]">
                                    {step.stderr_tail}
                                  </pre>
                                ) : null}
                              </div>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    </div>
                  </div>
                </>
              )}
            </Card>
          ) : null}
        </>
      )}
    </div>
  )
}
