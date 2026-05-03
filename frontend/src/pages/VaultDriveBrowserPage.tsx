import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Alert, Badge, Button, Card, Label, Spinner, TextInput } from 'flowbite-react'
import { HiArrowLeft, HiExternalLink, HiFolder, HiSearch } from 'react-icons/hi'
import {
  useVaultDriveAccounts,
  useVaultDriveChildrenInfinite,
  useVaultDriveSearch,
} from '../api/hooks'
import type { VaultDriveItem } from '../api/types'

type Crumb = { id: string | null; name: string }

function formatBytes(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`
  return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

function VaultItemRow({
  item,
  onOpenFolder,
}: {
  item: VaultDriveItem
  onOpenFolder: (id: string, name: string) => void
}) {
  return (
    <tr className="border-t border-slate-100 dark:border-slate-800">
      <td className="py-2 pr-2">
        {item.is_folder ? (
          <button
            type="button"
            className="inline-flex items-center gap-1.5 font-medium text-blue-600 dark:text-blue-400 hover:underline text-left"
            onClick={() => onOpenFolder(item.id, item.name)}
          >
            <HiFolder className="h-4 w-4 shrink-0" />
            {item.name}
          </button>
        ) : (
          <span className="font-medium text-slate-800 dark:text-slate-200">{item.name}</span>
        )}
      </td>
      <td className="py-2 text-xs text-slate-500 max-w-[12rem] truncate">{item.mime_type}</td>
      <td className="py-2 text-xs text-slate-600 dark:text-slate-400 whitespace-nowrap">
        {item.is_folder ? '—' : formatBytes(item.size)}
      </td>
      <td className="py-2 text-xs text-slate-500 whitespace-nowrap">{item.modified_time ?? '—'}</td>
      <td className="py-2 text-right">
        {item.web_view_link ? (
          <a
            href={item.web_view_link}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-blue-600 dark:text-blue-400 text-xs"
          >
            Drive <HiExternalLink className="h-3 w-3" />
          </a>
        ) : (
          <span className="text-slate-400">—</span>
        )}
      </td>
    </tr>
  )
}

function BrowserForAccount({ accountId, email }: { accountId: string; email: string }) {
  const navigate = useNavigate()
  const [path, setPath] = useState<Crumb[]>([{ id: null, name: 'Raíz bóveda' }])
  const parentId = path[path.length - 1]?.id ?? null

  const [searchInput, setSearchInput] = useState('')
  const [searchActive, setSearchActive] = useState(false)

  const childrenQ = useVaultDriveChildrenInfinite(accountId, parentId)
  const searchQ = useVaultDriveSearch(accountId, searchInput)

  const flatItems = useMemo(
    () => childrenQ.data?.pages.flatMap((p) => p.items) ?? [],
    [childrenQ.data?.pages],
  )

  function goFolder(id: string, name: string) {
    setPath((p) => [...p, { id, name }])
    setSearchActive(false)
  }

  function goCrumb(idx: number) {
    setPath((p) => p.slice(0, idx + 1))
    setSearchActive(false)
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Button color="light" size="sm" onClick={() => navigate('/vault-drive')}>
          <HiArrowLeft className="h-4 w-4 mr-2" /> Cuentas
        </Button>
        <h1 className="text-xl font-semibold">Bóveda en Drive</h1>
        <Badge color="info">{email}</Badge>
      </div>

      <p className="text-sm text-slate-500 dark:text-slate-400 max-w-3xl">
        Contenido de la Shared Drive bajo la carpeta de la cuenta (1-GMAIL, 2-DRIVE, 3-REPORTS, etc.). Requiere{' '}
        <code className="text-xs">vault_drive.view_all</code> o{' '}
        <code className="text-xs">vault_drive.view_delegated</code> con delegación en Usuarios.
      </p>

      <Card>
        <div className="flex flex-wrap items-center gap-2 text-sm mb-3">
          {path.map((c, i) => (
            <span key={`${c.id ?? 'root'}-${i}`} className="inline-flex items-center gap-1">
              {i > 0 ? <span className="text-slate-400">/</span> : null}
              <button
                type="button"
                className={
                  i === path.length - 1
                    ? 'font-semibold text-slate-900 dark:text-white'
                    : 'text-blue-600 dark:text-blue-400 hover:underline'
                }
                onClick={() => i < path.length - 1 && goCrumb(i)}
                disabled={i === path.length - 1}
              >
                {c.name}
              </button>
            </span>
          ))}
        </div>

        <div className="flex flex-wrap gap-3 items-end mb-4">
          <div className="flex-1 min-w-[220px]">
            <Label value="Buscar en el árbol (nombre, acotado)" className="mb-1" />
            <TextInput
              icon={HiSearch}
              type="search"
              placeholder="Mínimo 2 caracteres…"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
            />
          </div>
          <Button
            color="light"
            size="sm"
            disabled={searchInput.trim().length < 2}
            onClick={() => setSearchActive(true)}
          >
            Buscar
          </Button>
          {searchActive ? (
            <Button color="gray" size="sm" onClick={() => setSearchActive(false)}>
              Ver carpeta actual
            </Button>
          ) : null}
        </div>

        {searchActive ? (
          searchQ.isLoading ? (
            <Spinner />
          ) : searchQ.isError ? (
            <Alert color="failure">{(searchQ.error as Error)?.message ?? 'Error en búsqueda'}</Alert>
          ) : (
            <>
              {searchQ.data?.truncated ? (
                <Alert color="warning" className="mb-3">
                  Resultados truncados (límite de seguridad). Acotá el criterio o navegá por carpetas.
                </Alert>
              ) : null}
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="text-left text-slate-500">
                    <tr>
                      <th className="py-2">Nombre</th>
                      <th className="py-2">Tipo</th>
                      <th className="py-2">Tamaño</th>
                      <th className="py-2">Modificado</th>
                      <th className="py-2 text-right">Abrir</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(searchQ.data?.items ?? []).map((item) => (
                      <VaultItemRow key={item.id} item={item} onOpenFolder={goFolder} />
                    ))}
                  </tbody>
                </table>
              </div>
              {!searchQ.data?.items.length ? (
                <p className="text-slate-500 text-sm mt-2">Sin coincidencias.</p>
              ) : null}
            </>
          )
        ) : childrenQ.isError ? (
          <Alert color="failure">{(childrenQ.error as Error)?.message ?? 'Error listando carpeta'}</Alert>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="text-left text-slate-500">
                  <tr>
                    <th className="py-2">Nombre</th>
                    <th className="py-2">Tipo</th>
                    <th className="py-2">Tamaño</th>
                    <th className="py-2">Modificado</th>
                    <th className="py-2 text-right">Abrir</th>
                  </tr>
                </thead>
                <tbody>
                  {flatItems.map((item) => (
                    <VaultItemRow key={item.id} item={item} onOpenFolder={goFolder} />
                  ))}
                </tbody>
              </table>
            </div>
            {childrenQ.isFetching && !childrenQ.isFetchingNextPage ? <Spinner className="mt-3" /> : null}
            {!childrenQ.isLoading && !flatItems.length ? (
              <p className="text-slate-500 text-sm mt-2">Carpeta vacía.</p>
            ) : null}
            {childrenQ.hasNextPage ? (
              <Button
                className="mt-3"
                color="light"
                size="sm"
                isProcessing={childrenQ.isFetchingNextPage}
                onClick={() => void childrenQ.fetchNextPage()}
              >
                Cargar más
              </Button>
            ) : null}
          </>
        )}
      </Card>
    </div>
  )
}

export default function VaultDriveBrowserPage() {
  const { accountId } = useParams<{ accountId?: string }>()
  const navigate = useNavigate()
  const accountsQ = useVaultDriveAccounts()

  const id = accountId ?? null
  const picked = useMemo(
    () => (id ? (accountsQ.data ?? []).find((a) => a.id === id) : null),
    [accountsQ.data, id],
  )

  if (id && accountsQ.isLoading) {
    return <Spinner />
  }

  if (id && accountsQ.isSuccess && !picked) {
    return (
      <div className="space-y-4">
        <Alert color="failure">
          Cuenta no disponible para tu usuario o sin carpeta vault configurada.
        </Alert>
        <Button color="light" onClick={() => navigate('/vault-drive')}>
          Volver al listado
        </Button>
      </div>
    )
  }

  if (id && picked) {
    return <BrowserForAccount accountId={id} email={picked.email} />
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Button color="light" size="sm" onClick={() => navigate('/accounts')}>
          <HiArrowLeft className="h-4 w-4 mr-2" /> Cuentas
        </Button>
        <h1 className="text-xl font-semibold">Bóveda Drive · elegir cuenta</h1>
      </div>
      <p className="text-sm text-slate-500 dark:text-slate-400 max-w-3xl">
        Explorador del contenido que la plataforma guarda en la Shared Drive para cada usuario. Los permisos son
        independientes del visor de correo.
      </p>
      {accountsQ.isLoading ? (
        <Spinner />
      ) : accountsQ.isError ? (
        <Alert color="failure">{(accountsQ.error as Error)?.message ?? 'Error'}</Alert>
      ) : (accountsQ.data ?? []).length === 0 ? (
        <p className="text-slate-500 text-sm">No hay cuentas visibles o falta configurar la carpeta vault.</p>
      ) : (
        <Card>
          <ul className="divide-y divide-slate-200 dark:divide-slate-700">
            {(accountsQ.data ?? []).map((a) => (
              <li key={a.id} className="py-3 flex flex-wrap items-center justify-between gap-2">
                <div>
                  <Link
                    to={`/vault-drive/${a.id}`}
                    className="font-medium text-blue-600 dark:text-blue-400 hover:underline"
                  >
                    {a.email}
                  </Link>
                  <div className="text-xs text-slate-500 mt-0.5">Google Drive · bóveda de respaldos</div>
                </div>
                <Button size="xs" color="light" onClick={() => navigate(`/vault-drive/${a.id}`)}>
                  Abrir
                </Button>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  )
}
