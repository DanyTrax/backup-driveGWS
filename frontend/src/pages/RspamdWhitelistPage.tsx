import { useMemo, useState } from 'react'
import { Badge, Button, Card, Checkbox, Label, TextInput } from 'flowbite-react'
import toast from 'react-hot-toast'
import {
  useAddRspamdWhitelistEntry,
  useBulkDeleteRspamdWhitelist,
  useRspamdWhitelist,
  useRspamdWhitelistPreview,
} from '../api/hooks'
import { useAuthStore } from '../stores/auth'

const PAGE_SIZES = [10, 25, 50, 100] as const

export default function RspamdWhitelistPage() {
  const hasPermission = useAuthStore((s) => s.hasPermission)
  const canView = hasPermission('rspamd_whitelist.view')
  const canEdit = hasPermission('rspamd_whitelist.edit')

  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)
  const [search, setSearch] = useState('')
  const [q, setQ] = useState('')
  const [newRule, setNewRule] = useState('')
  const [selected, setSelected] = useState<Set<string>>(() => new Set())

  const listQ = useRspamdWhitelist(page, pageSize, q)
  const previewQ = useRspamdWhitelistPreview()
  const addM = useAddRspamdWhitelistEntry()
  const deleteM = useBulkDeleteRspamdWhitelist()

  const items = listQ.data?.items ?? []
  const total = listQ.data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  const allSelected = useMemo(
    () => items.length > 0 && items.every((r) => selected.has(r.id)),
    [items, selected],
  )

  function toggleOne(id: string) {
    setSelected((prev) => {
      const n = new Set(prev)
      if (n.has(id)) n.delete(id)
      else n.add(id)
      return n
    })
  }

  function toggleAll() {
    if (allSelected) {
      setSelected(new Set())
      return
    }
    setSelected(new Set(items.map((r) => r.id)))
  }

  function applySearch() {
    setQ(search)
    setPage(1)
    setSelected(new Set())
  }

  async function onAdd() {
    const raw = newRule.trim()
    if (!raw) {
      toast.error('Escribí una regla (dominio, @dominio o correo).')
      return
    }
    try {
      await addM.mutateAsync(raw)
      toast.success('Regla agregada. Rspamd la verá en ~5 min.')
      setNewRule('')
      setSelected(new Set())
    } catch (err: unknown) {
      const st = (err as { response?: { status?: number; data?: { detail?: { message?: string } } } })
        ?.response?.status
      const msg = (err as { response?: { data?: { detail?: { message?: string } } } })?.response?.data?.detail
        ?.message
      if (st === 403) toast.error('Sin permiso (rspamd_whitelist.edit).')
      else if (st === 409) toast.error('Esa regla ya existe.')
      else if (st === 400) toast.error(msg || 'Regla inválida.')
      else toast.error('No se pudo agregar.')
    }
  }

  async function onBulkDelete() {
    if (selected.size === 0) {
      toast.error('Seleccioná al menos una fila.')
      return
    }
    if (!window.confirm(`¿Eliminar ${selected.size} regla(s) de la lista blanca?`)) return
    try {
      await deleteM.mutateAsync([...selected])
      toast.success('Eliminadas. Rspamd actualizará en ~5 min.')
      setSelected(new Set())
    } catch (err: unknown) {
      const st = (err as { response?: { status?: number } })?.response?.status
      if (st === 403) toast.error('Sin permiso (rspamd_whitelist.edit).')
      else toast.error('No se pudo eliminar.')
    }
  }

  if (!canView) {
    return (
      <Card>
        <p className="text-slate-600 dark:text-slate-400">
          Sin permiso <code className="text-xs">rspamd_whitelist.view</code>. Pedí acceso en Roles.
        </p>
      </Card>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Lista blanca Rspamd</h1>
        <p className="text-slate-500 text-sm max-w-3xl mt-1">
          Direcciones y dominios que <strong>nunca</strong> deben penalizarse como spam en Mailcow (símbolo{' '}
          <code className="text-xs">PLATAFORMA_FROM_*</code>). Podés usar{' '}
          <code className="text-xs">dominio.com</code>, <code className="text-xs">@dominio.com</code>,{' '}
          <code className="text-xs">*@dominio.com</code> o <code className="text-xs">user@dominio.com</code>.
          Los cambios llegan a Rspamd en unos 5 minutos; no hace falta reiniciar Mailcow.
        </p>
      </div>

      {previewQ.data ? (
        <Card className="text-sm">
          <p className="text-slate-500 dark:text-slate-400">
            Fuente activa del feed:{' '}
            <Badge color={previewQ.data.source === 'database' ? 'success' : 'warning'}>
              {previewQ.data.source === 'database' ? 'Panel (base de datos)' : '.env (PoC)'}
            </Badge>
            {' · '}
            {previewQ.data.entry_count} entrada(s) — dominios: {previewQ.data.domains.length}, correos:{' '}
            {previewQ.data.emails.length}
          </p>
        </Card>
      ) : null}

      {canEdit ? (
        <Card>
          <div className="flex flex-wrap gap-3 items-end">
            <div className="grow min-w-[240px] max-w-xl">
              <Label htmlFor="new-rule" value="Nueva regla" />
              <TextInput
                id="new-rule"
                placeholder="*@ejemplo.com"
                value={newRule}
                onChange={(e) => setNewRule(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') void onAdd()
                }}
              />
            </div>
            <Button onClick={() => void onAdd()} disabled={addM.isPending}>
              Agregar elemento
            </Button>
          </div>
        </Card>
      ) : (
        <p className="text-sm text-amber-700 dark:text-amber-400">
          Solo lectura: tu rol tiene <code className="text-xs">rspamd_whitelist.view</code> pero no{' '}
          <code className="text-xs">rspamd_whitelist.edit</code>.
        </p>
      )}

      <Card>
        <div className="flex flex-wrap gap-3 items-end justify-between mb-4">
          <div className="flex flex-wrap gap-2 items-end">
            <div>
              <Label htmlFor="wl-search" value="Buscar" />
              <TextInput
                id="wl-search"
                placeholder="dominio o correo…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') applySearch()
                }}
              />
            </div>
            <Button color="gray" onClick={applySearch}>
              Buscar
            </Button>
          </div>
          <div className="flex items-center gap-2">
            <Label htmlFor="page-size" value="Mostrar" className="sr-only" />
            <select
              id="page-size"
              className="rounded-lg border border-slate-300 bg-slate-50 text-sm dark:border-slate-600 dark:bg-slate-700"
              value={pageSize}
              onChange={(e) => {
                setPageSize(Number(e.target.value))
                setPage(1)
                setSelected(new Set())
              }}
            >
              {PAGE_SIZES.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
            <span className="text-sm text-slate-500">por página</span>
          </div>
        </div>

        {listQ.isLoading ? (
          <p className="text-slate-500">Cargando…</p>
        ) : listQ.isError ? (
          <p className="text-red-600">No se pudo cargar la lista.</p>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="text-left text-slate-500 border-b border-slate-200 dark:border-slate-700">
                  <tr>
                    {canEdit ? (
                      <th className="py-2 pr-2 w-8">
                        <Checkbox checked={allSelected} onChange={toggleAll} aria-label="Seleccionar todo" />
                      </th>
                    ) : null}
                    <th className="py-2 pr-3">Regla</th>
                    <th className="py-2 pr-3">Normalizado</th>
                    <th className="py-2 pr-3">Tipo</th>
                    <th className="py-2 pr-3">Mapa</th>
                    <th className="py-2 pr-3">Creado por</th>
                    <th className="py-2">Fecha</th>
                  </tr>
                </thead>
                <tbody>
                  {items.length === 0 ? (
                    <tr>
                      <td
                        colSpan={canEdit ? 7 : 6}
                        className="py-8 text-center text-slate-500"
                      >
                        {q
                          ? 'Sin resultados para la búsqueda.'
                          : 'Lista vacía. Agregá reglas o definí RSPAMD_WHITELIST_ENTRIES en .env hasta migrar.'}
                      </td>
                    </tr>
                  ) : (
                    items.map((row) => (
                      <tr
                        key={row.id}
                        className="border-b border-slate-100 dark:border-slate-800 odd:bg-slate-50/50 dark:odd:bg-slate-900/30"
                      >
                        {canEdit ? (
                          <td className="py-2 pr-2">
                            <Checkbox
                              checked={selected.has(row.id)}
                              onChange={() => toggleOne(row.id)}
                              aria-label={`Seleccionar ${row.raw_input}`}
                            />
                          </td>
                        ) : null}
                        <td className="py-2 pr-3 font-mono text-xs">{row.raw_input}</td>
                        <td className="py-2 pr-3 font-mono text-xs">{row.value}</td>
                        <td className="py-2 pr-3">
                          <Badge color={row.kind === 'domain' ? 'info' : 'purple'}>
                            {row.kind === 'domain' ? 'Dominio' : 'Correo'}
                          </Badge>
                        </td>
                        <td className="py-2 pr-3 text-xs text-slate-500">{row.map_file}</td>
                        <td className="py-2 pr-3 text-xs">{row.created_by_email ?? '—'}</td>
                        <td className="py-2 text-xs text-slate-500 whitespace-nowrap">
                          {new Date(row.created_at).toLocaleString()}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 mt-4 text-sm text-slate-500">
              <span>
                Mostrando {total === 0 ? 0 : (page - 1) * pageSize + 1} a{' '}
                {Math.min(page * pageSize, total)} de {total}
              </span>
              <div className="flex flex-wrap gap-2 items-center">
                <Button
                  size="xs"
                  color="gray"
                  disabled={page <= 1}
                  onClick={() => {
                    setPage((p) => Math.max(1, p - 1))
                    setSelected(new Set())
                  }}
                >
                  Anterior
                </Button>
                <span>
                  Página {page} / {totalPages}
                </span>
                <Button
                  size="xs"
                  color="gray"
                  disabled={page >= totalPages}
                  onClick={() => {
                    setPage((p) => Math.min(totalPages, p + 1))
                    setSelected(new Set())
                  }}
                >
                  Siguiente
                </Button>
                {canEdit ? (
                  <>
                    <Button size="xs" color="gray" onClick={toggleAll}>
                      {allSelected ? 'Quitar selección' : 'Seleccionar todo'}
                    </Button>
                    <Button
                      size="xs"
                      color="failure"
                      disabled={selected.size === 0 || deleteM.isPending}
                      onClick={() => void onBulkDelete()}
                    >
                      Eliminar ({selected.size})
                    </Button>
                  </>
                ) : null}
              </div>
            </div>
          </>
        )}
      </Card>
    </div>
  )
}
