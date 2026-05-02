import { Link, useNavigate, useParams } from 'react-router-dom'
import { Alert, Button, Card, Spinner } from 'flowbite-react'
import { HiArrowLeft } from 'react-icons/hi'
import GybWorkAccountViewer from '../components/GybWorkAccountViewer'
import { useGybWorkAccounts } from '../api/hooks'

export default function GybVaultWorkBrowserPage() {
  const { accountId } = useParams<{ accountId?: string }>()
  const navigate = useNavigate()
  const id = accountId ?? null

  const accountsQ = useGybWorkAccounts('gyb-vault-work')
  const accounts = accountsQ.data ?? []

  if (id) {
    return <GybWorkAccountViewer accountId={id} variant="standalone" source="vault" />
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Button color="light" size="sm" onClick={() => navigate('/accounts')}>
          <HiArrowLeft className="h-4 w-4 mr-2" /> Cuentas
        </Button>
        <h1 className="text-xl font-semibold">Bandeja GYB · copia en Google Drive</h1>
      </div>
      <p className="text-sm text-slate-500 dark:text-slate-400 max-w-3xl">
        Misma interfaz que «GYB trabajo», pero leyendo los <code className="text-xs">.eml</code> bajo{' '}
        <code className="text-xs">1-GMAIL/gyb_mbox</code> en la carpeta vault de la cuenta (
        <code className="text-xs">drive_vault_folder_id</code>) vía rclone. No usa la carpeta local del worker. La
        vista por etiquetas Gmail (<code className="text-xs">msg-db.sqlite</code>) no está disponible aquí: usá la
        bandeja de trabajo local para eso.
      </p>
      {accountsQ.isLoading ? (
        <Spinner />
      ) : accountsQ.isError ? (
        <Alert color="failure">{(accountsQ.error as Error)?.message ?? 'Error cargando cuentas'}</Alert>
      ) : accounts.length === 0 ? (
        <p className="text-slate-500 text-sm">
          Ninguna cuenta tiene configurada la carpeta vault en Drive o no tenés delegación para verla.
        </p>
      ) : (
        <Card>
          <h2 className="text-sm font-medium mb-3">Elegí una cuenta</h2>
          <ul className="divide-y divide-slate-200 dark:divide-slate-700">
            {accounts.map((a) => (
              <li key={a.id} className="py-3 flex flex-wrap items-center justify-between gap-2">
                <div>
                  <Link
                    to={`/gyb-vault-work/${a.id}`}
                    className="font-medium text-blue-600 dark:text-blue-400 hover:underline"
                  >
                    {a.email}
                  </Link>
                  <div className="text-xs text-slate-500 mt-0.5">Lectura remota · rclone</div>
                </div>
                <Button size="xs" color="light" onClick={() => navigate(`/gyb-vault-work/${a.id}`)}>
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
