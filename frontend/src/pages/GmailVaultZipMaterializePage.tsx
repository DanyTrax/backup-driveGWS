import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Alert, Badge, Button, Card, Label, Select, Spinner, TextInput } from 'flowbite-react'
import { HiArrowLeft } from 'react-icons/hi'
import toast from 'react-hot-toast'
import type { AxiosError } from 'axios'

import {
  useCreateGmailVaultMaterialize,
  useDeleteGmailVaultMaterialize,
  useGmailVaultMaterializeSession,
  useProfile,
  useTasks,
  useVaultDriveAccounts,
} from '../api/hooks'
import type { BackupTask, GmailVaultMaterializeCreatePayload, GmailVaultMaterializeMode } from '../api/types'

function thisMonthYyyyMm(): string {
  const d = new Date()
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  return `${y}-${m}`
}

function todayYyyyMmDd(): string {
  const d = new Date()
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function formatApiErr(err: unknown): string {
  const ax = err as AxiosError<{ detail?: unknown }>
  const d = ax.response?.data?.detail
  if (typeof d === 'string') return d
  if (d != null && typeof d === 'object') return JSON.stringify(d)
  return ax.message ?? 'Error'
}

export default function GmailVaultZipMaterializePage() {
  const navigate = useNavigate()
  const { accountId: routeAccountId } = useParams<{ accountId?: string }>()
  const { data: profile } = useProfile()
  const canViewTasks = Boolean(profile?.permissions?.includes('tasks.view'))
  const accountsQ = useVaultDriveAccounts()
  const tasksQ = useTasks({ enabled: canViewTasks })

  const [accountId, setAccountId] = useState(routeAccountId ?? '')
  useEffect(() => {
    if (routeAccountId) setAccountId(routeAccountId)
  }, [routeAccountId])

  const [mode, setMode] = useState<GmailVaultMaterializeMode>('month')
  const [anchorDate, setAnchorDate] = useState(todayYyyyMmDd())
  const [dateFrom, setDateFrom] = useState(todayYyyyMmDd())
  const [dateTo, setDateTo] = useState(todayYyyyMmDd())
  const [calendarMonth, setCalendarMonth] = useState(thisMonthYyyyMm)
  const [taskId, setTaskId] = useState('')
  const [ttlDays, setTtlDays] = useState('')
  const [sessionId, setSessionId] = useState<string | null>(null)

  const sessionQ = useGmailVaultMaterializeSession(sessionId)
  const createMut = useCreateGmailVaultMaterialize()
  const deleteMut = useDeleteGmailVaultMaterialize()

  const gmailLinkedTasks = useMemo(() => {
    const list = tasksQ.data ?? []
    if (!accountId) return [] as BackupTask[]
    return list.filter(
      (t) =>
        (t.scope === 'gmail' || t.scope === 'full') && (t.account_ids ?? []).includes(accountId),
    )
  }, [tasksQ.data, accountId])

  useEffect(() => {
    if (taskId && !gmailLinkedTasks.some((t) => t.id === taskId)) {
      setTaskId('')
    }
  }, [gmailLinkedTasks, taskId])

  async function submit() {
    if (!accountId.trim()) {
      toast.error('Elegí una cuenta.')
      return
    }

    const payload: GmailVaultMaterializeCreatePayload = {
      account_id: accountId.trim(),
      mode,
    }
    if (taskId.trim()) payload.task_id = taskId.trim()
    const ttlNum = parseInt(ttlDays, 10)
    if (!Number.isNaN(ttlNum) && ttlNum > 0) payload.ttl_days = ttlNum

    if (mode === 'single_day') {
      payload.anchor_date = anchorDate
    } else if (mode === 'date_range') {
      payload.date_from = dateFrom
      payload.date_to = dateTo
    } else if (mode === 'month') {
      payload.calendar_month = calendarMonth
    }

    try {
      const row = await createMut.mutateAsync(payload)
      setSessionId(row.id)
      toast.success('Sesión creada; descarga en segundo plano (Celery).')
    } catch (err) {
      toast.error(`No se pudo crear la sesión: ${formatApiErr(err).slice(0, 380)}`)
    }
  }

  async function removeSession() {
    if (!sessionId) return
    try {
      await deleteMut.mutateAsync(sessionId)
      setSessionId(null)
      toast.success('Sesión eliminada en servidor.')
    } catch (err) {
      toast.error(`No se pudo eliminar: ${formatApiErr(err).slice(0, 380)}`)
    }
  }

  const sess = sessionQ.data
  const busy = sess?.status === 'pending' || sess?.status === 'downloading'

  if (!routeAccountId && accountsQ.isLoading) {
    return <Spinner />
  }

  if (routeAccountId && accountsQ.isLoading) {
    return <Spinner />
  }

  if (
    routeAccountId &&
    accountsQ.isSuccess &&
    !(accountsQ.data ?? []).some((a) => a.id === routeAccountId)
  ) {
    return (
      <div className="space-y-4">
        <Alert color="failure">Cuenta no disponible para tu usuario o sin bóveda configurada.</Alert>
        <Button color="light" onClick={() => navigate('/vault-gmail-zip')}>
          Volver al listado
        </Button>
      </div>
    )
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex flex-wrap items-center gap-3">
        <Button color="light" size="sm" onClick={() => navigate('/vault-drive')}>
          <HiArrowLeft className="h-4 w-4 mr-2" /> Bóveda Drive
        </Button>
        <h1 className="text-xl font-semibold">Materializar ZIPs Gmail (vault)</h1>
      </div>

      <p className="text-sm text-slate-500 dark:text-slate-400">
        Descarga al servidor los archivos <code className="text-xs">1-GMAIL/zips/…</code> que cubren el rango
        elegido, y los deja extraídos bajo la ruta local de la sesión. Requiere worker Celery y permisos de bóveda
        Drive. El TTL por defecto lo define el servidor; podés acotar días debajo del máximo configurado.
      </p>

      {!routeAccountId ? (
        <Card>
          <h2 className="text-lg font-medium mb-3">Elegir cuenta</h2>
          {accountsQ.isError ? (
            <Alert color="failure">{(accountsQ.error as Error)?.message ?? 'Error'}</Alert>
          ) : (accountsQ.data ?? []).length === 0 ? (
            <p className="text-sm text-slate-500">No hay cuentas visibles con bóveda.</p>
          ) : (
            <ul className="divide-y divide-slate-200 dark:divide-slate-700">
              {(accountsQ.data ?? []).map((a) => (
                <li key={a.id} className="py-2 flex flex-wrap justify-between gap-2 items-center">
                  <span className="font-medium">{a.email}</span>
                  <Button size="xs" onClick={() => navigate(`/vault-gmail-zip/${a.id}`)}>
                    Usar esta cuenta
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      ) : null}

      {routeAccountId || accountId ? (
        <Card>
          <h2 className="text-lg font-medium mb-4">Nueva materialización</h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {!routeAccountId ? (
              <div className="md:col-span-2">
                <Label value="Cuenta (UUID o elegir arriba)" />
                <TextInput value={accountId} onChange={(e) => setAccountId(e.target.value)} className="mt-1" />
              </div>
            ) : (
              <div className="md:col-span-2 text-sm text-slate-600 dark:text-slate-400">
                Cuenta:{' '}
                <Badge color="info">{(accountsQ.data ?? []).find((x) => x.id === accountId)?.email ?? accountId}</Badge>
              </div>
            )}

            <div>
              <Label value="Modo" />
              <Select
                className="mt-1"
                value={mode}
                onChange={(e) => setMode(e.target.value as GmailVaultMaterializeMode)}
              >
                <option value="single_day">Un día (anchor_date)</option>
                <option value="date_range">Rango (date_from … date_to)</option>
                <option value="month">Mes calendario (YYYY-MM)</option>
                <option value="all">Todo (zip con nombre válido bajo la cuenta)</option>
              </Select>
            </div>

            {mode === 'single_day' ? (
              <div>
                <Label value="Día" />
                <TextInput type="date" value={anchorDate} onChange={(e) => setAnchorDate(e.target.value)} className="mt-1" />
              </div>
            ) : null}

            {mode === 'date_range' ? (
              <>
                <div>
                  <Label value="Desde" />
                  <TextInput type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="mt-1" />
                </div>
                <div>
                  <Label value="Hasta" />
                  <TextInput type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="mt-1" />
                </div>
              </>
            ) : null}

            {mode === 'month' ? (
              <div>
                <Label value="Mes (YYYY-MM)" />
                <TextInput
                  value={calendarMonth}
                  onChange={(e) => setCalendarMonth(e.target.value)}
                  placeholder="2026-05"
                  className="mt-1"
                />
              </div>
            ) : null}

            {mode === 'all' ? (
              <div className="md:col-span-2 text-xs text-slate-500">
                Modo «todo»: se consideran todos los periodos nombrados{' '}
                <code>YYYY-MM-DD__YYYY-MM-DD.zip</code> bajo <code>1-GMAIL/zips/&lt;cuenta&gt;/</code>.
              </div>
            ) : null}

            <div className="md:col-span-2">
              <Label value="Tarea Gmail/Full (opcional, auditoría y validación)" />
              <Select
                className="mt-1"
                value={taskId}
                onChange={(e) => setTaskId(e.target.value)}
                disabled={!accountId || tasksQ.isLoading || !canViewTasks}
              >
                <option value="">— Ninguna —</option>
                {gmailLinkedTasks.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} ({t.scope})
                  </option>
                ))}
              </Select>
              {!canViewTasks ? (
                <p className="text-xs text-slate-500 mt-1">
                  Sin <code className="text-xs">tasks.view</code> no se listan tareas; podés dejar la tarea vacía.
                </p>
              ) : null}
            </div>

            <div>
              <Label value="TTL (días, opcional)" />
              <TextInput
                type="number"
                min={1}
                placeholder="default servidor"
                value={ttlDays}
                onChange={(e) => setTtlDays(e.target.value)}
                className="mt-1"
              />
            </div>
          </div>

          <div className="mt-4 flex flex-wrap gap-2">
            <Button onClick={() => void submit()} disabled={!accountId || createMut.isPending}>
              {createMut.isPending ? 'Creando…' : 'Iniciar materialización'}
            </Button>
            {routeAccountId ? (
              <Link to="/vault-gmail-zip" className="inline-flex items-center text-sm text-blue-600 dark:text-blue-400">
                Cambiar cuenta
              </Link>
            ) : null}
          </div>
        </Card>
      ) : null}

      {sessionId ? (
        <Card>
          <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
            <h2 className="text-lg font-medium">Sesión activa</h2>
            <Badge color={busy ? 'warning' : sess?.status === 'ready' ? 'success' : 'failure'}>
              {sessionQ.isLoading ? '…' : sess?.status ?? '—'}
            </Badge>
          </div>

          {sessionQ.isError ? (
            <Alert color="failure">
              {(sessionQ.error as Error)?.message ?? 'Error al leer sesión'}
              {(sessionQ.error as AxiosError)?.response?.status === 404 ? (
                <span className="block mt-2 text-sm">Puede haber expirado el TTL; creá una nueva sesión.</span>
              ) : null}
            </Alert>
          ) : sessionQ.isLoading && !sess ? (
            <Spinner />
          ) : sess ? (
            <div className="space-y-3 text-sm">
              <p>
                <span className="text-slate-500">ID:</span> <code className="text-xs">{sess.id}</code>
              </p>
              <p>
                <span className="text-slate-500">Ventana:</span> {sess.date_from ?? '—'} → {sess.date_to ?? '—'} · modo{' '}
                {sess.requested_mode}
              </p>
              <p>
                <span className="text-slate-500">Caduca:</span> {sess.ttl_expires_at}
              </p>
              <p>
                <span className="text-slate-500">Ruta local (VPS):</span>{' '}
                <code className="text-xs break-all">{sess.path_local}</code>
              </p>
              {sess.error_summary ? (
                <Alert color="failure">
                  <span className="font-mono text-xs whitespace-pre-wrap">{sess.error_summary}</span>
                </Alert>
              ) : null}
              <details className="rounded border border-slate-200 dark:border-slate-700 p-2">
                <summary className="cursor-pointer text-slate-600 dark:text-slate-400">progress_json</summary>
                <pre className="mt-2 text-xs overflow-x-auto max-h-64 overflow-y-auto">
                  {JSON.stringify(sess.progress_json ?? {}, null, 2)}
                </pre>
              </details>
              <Button color="failure" size="sm" onClick={() => void removeSession()} disabled={deleteMut.isPending}>
                Eliminar sesión y datos locales
              </Button>
            </div>
          ) : null}
        </Card>
      ) : null}
    </div>
  )
}
