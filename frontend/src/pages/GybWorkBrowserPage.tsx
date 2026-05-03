import { Link, useNavigate, useParams } from 'react-router-dom'
import { Alert, Button, Card, Spinner } from 'flowbite-react'
import { HiArrowLeft } from 'react-icons/hi'
import GybWorkAccountViewer from '../components/GybWorkAccountViewer'
import { useGybWorkAccounts } from '../api/hooks'

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

export default function GybWorkBrowserPage() {
  const { accountId } = useParams<{ accountId?: string }>()
  const navigate = useNavigate()
  const id = accountId ?? null

  const accountsQ = useGybWorkAccounts()
  const accounts = accountsQ.data ?? []

  if (id) {
    return (
      <div className="flex min-h-0 flex-1 flex-col">
        <GybWorkAccountViewer accountId={id} variant="standalone" />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Button color="light" size="sm" onClick={() => navigate('/accounts')}>
          <HiArrowLeft className="h-4 w-4 mr-2" /> Cuentas
        </Button>
        <h1 className="text-xl font-semibold">Bandeja de trabajo GYB</h1>
      </div>
      <p className="text-sm text-slate-500 dark:text-slate-400 max-w-3xl">
        Solo se listan cuentas con export <code className="text-xs">.eml</code> o{' '}
        <code className="text-xs">.mbox</code> en <code className="text-xs">/var/msa/work/gmail/…</code>. La lectura
        no usa Maildir: es el volcado local del worker GYB. Mismos permisos que el visor Maildir (
        <code className="text-xs">mailbox.view_all</code> o delegación).
      </p>
      {accountsQ.isLoading ? (
        <Spinner />
      ) : accountsQ.isError ? (
        <Alert color="failure">{(accountsQ.error as Error)?.message ?? 'Error cargando cuentas'}</Alert>
      ) : accounts.length === 0 ? (
        <p className="text-slate-500 text-sm">Ninguna cuenta tiene carpeta de trabajo GYB con mensajes exportados.</p>
      ) : (
        <Card>
          <h2 className="text-sm font-medium mb-3">Elegí una cuenta</h2>
          <ul className="divide-y divide-slate-200 dark:divide-slate-700">
            {accounts.map((a) => (
              <li key={a.id} className="py-3 flex flex-wrap items-center justify-between gap-2">
                <div>
                  <Link to={`/gyb-work/${a.id}`} className="font-medium text-blue-600 dark:text-blue-400 hover:underline">
                    {a.email}
                  </Link>
                  <div className="text-xs text-slate-500 mt-0.5">
                    {a.work_size_bytes != null ? formatBytes(a.work_size_bytes) : '—'}
                    {a.has_msg_db ? ' · msg-db.sqlite' : ''}
                  </div>
                </div>
                <Button size="xs" color="light" onClick={() => navigate(`/gyb-work/${a.id}`)}>
                  Abrir mensajes
                </Button>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  )
}
