import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  Alert,
  Badge,
  Button,
  Card,
  Checkbox,
  Label,
  Select,
  Spinner,
  Textarea,
  TextInput,
} from 'flowbite-react'
import toast from 'react-hot-toast'
import { HiArrowLeft, HiMenu, HiSearch, HiX } from 'react-icons/hi'
import { downloadGybWorkAttachment } from '../api/gybWorkAttachment'
import { useGybWorkAccounts, useGybWorkFolders, useGybWorkMessage, useGybWorkMessages } from '../api/hooks'
import type { MailboxMessageSummary } from '../api/types'

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

function reviewedStorageKey(accountId: string) {
  return `msa-gyb-reviewed-${accountId}`
}

function noteStorageKey(accountId: string, messageKey: string) {
  return `msa-gyb-note-${accountId}-${messageKey}`
}

function csvCell(s: string): string {
  return `"${s.replace(/"/g, '""')}"`
}

function wrapMailHtmlFragment(html: string): string {
  const safe = html.replace(/<\/script/gi, '<\\/script').replace(/<\/iframe/gi, '<\\/iframe')
  return `<!DOCTYPE html><html><head><meta charset="utf-8"/><base target="_blank" rel="noopener noreferrer"/><style>
body{font-family:system-ui,-apple-system,sans-serif;margin:0;padding:12px;word-wrap:break-word;color:rgb(30 41 59);}
@media (prefers-color-scheme:dark){body{color:rgb(226 232 240);background:#0f172a;}}
img,video{max-width:100%;height:auto;}pre{white-space:pre-wrap;}table{max-width:100%;}
</style></head><body>${safe}</body></html>`
}

export type GybWorkAccountViewerVariant = 'standalone' | 'embedded'

export type GybWorkAccountViewerProps = {
  accountId: string
  variant: GybWorkAccountViewerVariant
}

export default function GybWorkAccountViewer({ accountId: id, variant }: GybWorkAccountViewerProps) {
  const navigate = useNavigate()
  const [viewMode, setViewMode] = useState<'disk' | 'labels'>('labels')
  const [folderId, setFolderId] = useState('')
  const [labelId, setLabelId] = useState('')
  const [page, setPage] = useState(0)
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [searchInput, setSearchInput] = useState('')
  const [searchCommitted, setSearchCommitted] = useState('')
  const [listScope, setListScope] = useState<'folder' | 'all'>('folder')
  const [sortBy, setSortBy] = useState<'header_date' | 'mtime'>('header_date')
  const [sortOrder, setSortOrder] = useState<'desc' | 'asc'>('desc')
  const [reviewedIds, setReviewedIds] = useState<Set<string>>(() => new Set())
  const [noteDraft, setNoteDraft] = useState('')

  useEffect(() => {
    const t = window.setTimeout(() => setSearchCommitted(searchInput.trim()), 400)
    return () => window.clearTimeout(t)
  }, [searchInput])

  useEffect(() => {
    try {
      const raw = localStorage.getItem(reviewedStorageKey(id))
      setReviewedIds(new Set(raw ? (JSON.parse(raw) as string[]) : []))
    } catch {
      setReviewedIds(new Set())
    }
  }, [id])

  useEffect(() => {
    if (!selectedKey) {
      setNoteDraft('')
      return
    }
    setNoteDraft(localStorage.getItem(noteStorageKey(id, selectedKey)) ?? '')
  }, [id, selectedKey])

  const toggleReviewed = useCallback(
    (key: string | null) => {
      if (!key) return
      setReviewedIds((prev) => {
        const next = new Set(prev)
        if (next.has(key)) next.delete(key)
        else next.add(key)
        try {
          localStorage.setItem(reviewedStorageKey(id), JSON.stringify([...next]))
        } catch {
          toast.error('No se pudo guardar “revisado” (almacenamiento lleno?)')
          return prev
        }
        return next
      })
    },
    [id],
  )

  const accountsQ = useGybWorkAccounts()
  const foldersQ = useGybWorkFolders(id, viewMode)
  const msgsQ = useGybWorkMessages(id, {
    view: viewMode,
    folderId,
    labelId,
    q: searchCommitted,
    offset: page * 80,
    listScope,
    sortBy,
    sortOrder,
  })
  const bodyQ = useGybWorkMessage(id, selectedKey)

  const folders = foldersQ.data ?? []
  const items = msgsQ.data?.items ?? []

  const pageRange = useMemo(() => {
    const total = msgsQ.data?.total_matches
    const start = items.length === 0 ? 0 : page * 80 + 1
    const end = page * 80 + items.length
    return {
      start,
      end,
      total: total ?? null,
      hasMore: msgsQ.data?.has_more ?? false,
    }
  }, [msgsQ.data?.total_matches, msgsQ.data?.has_more, items.length, page])

  const selectionLabel = useMemo(() => {
    if (listScope === 'all') {
      return viewMode === 'labels' ? 'Todas las etiquetas (msg-db)' : 'Todo el export en disco'
    }
    if (viewMode === 'labels') {
      const name = folders.find((f) => f.id === labelId)?.name
      return name ?? (labelId ? labelId : '—')
    }
    return folders.find((f) => f.id === folderId)?.name ?? (folderId ? folderId : '(raíz)')
  }, [folders, folderId, labelId, viewMode, listScope])

  const iframeSrcDoc = useMemo(
    () => (bodyQ.data?.text_html ? wrapMailHtmlFragment(bodyQ.data.text_html) : ''),
    [bodyQ.data?.text_html],
  )

  const currentAccountEmail = useMemo(() => accountsQ.data?.find((a) => a.id === id)?.email, [accountsQ.data, id])
  const currentHasMsgDb = useMemo(
    () => accountsQ.data?.find((a) => a.id === id)?.has_msg_db ?? false,
    [accountsQ.data, id],
  )

  useEffect(() => {
    setPage(0)
    setSelectedKey(null)
    setFolderId('')
    setLabelId('')
    setListScope('folder')
  }, [viewMode])

  useEffect(() => {
    if (!foldersQ.data?.length) return
    if (listScope === 'all') return
    if (viewMode === 'disk') {
      setFolderId((prev) =>
        foldersQ.data!.some((f) => f.id === prev) ? prev : (foldersQ.data![0]?.id ?? ''),
      )
    } else {
      setLabelId((prev) =>
        foldersQ.data!.some((f) => f.id === prev) ? prev : (foldersQ.data![0]?.id ?? ''),
      )
    }
  }, [foldersQ.data, viewMode, listScope])

  useEffect(() => {
    setPage(0)
    setSelectedKey(null)
  }, [id, folderId, labelId, searchCommitted, listScope, sortBy, sortOrder])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target
      if (
        t instanceof HTMLInputElement ||
        t instanceof HTMLTextAreaElement ||
        t instanceof HTMLSelectElement ||
        (t instanceof HTMLElement && t.isContentEditable)
      ) {
        return
      }
      if (items.length === 0) return

      if (e.key === 'j' || e.key === 'ArrowDown') {
        e.preventDefault()
        const idx = items.findIndex((x) => x.id === selectedKey)
        const next = idx < 0 ? 0 : Math.min(items.length - 1, idx + 1)
        setSelectedKey(items[next]!.id)
        return
      }
      if (e.key === 'k' || e.key === 'ArrowUp') {
        e.preventDefault()
        const idx = items.findIndex((x) => x.id === selectedKey)
        const next = idx <= 0 ? 0 : idx - 1
        setSelectedKey(items[next]!.id)
        return
      }
      if (e.key === 'r' || e.key === 'R') {
        e.preventDefault()
        toggleReviewed(selectedKey ?? items[0]?.id ?? null)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [items, selectedKey, toggleReviewed])

  function downloadCurrentPageCsv() {
    if (items.length === 0) {
      toast.error('No hay filas para exportar en esta página')
      return
    }
    const header = ['subject', 'from', 'date', 'size', 'labels', 'reviewed', 'id']
    const lines = [
      header.join(','),
      ...items.map((m) => {
        const labs = (m.labels ?? []).join('; ')
        const rev = m.id && reviewedIds.has(m.id) ? 'yes' : 'no'
        return [
          csvCell(m.subject),
          csvCell(m.from),
          csvCell(m.date ?? ''),
          String(m.size),
          csvCell(labs),
          rev,
          csvCell(m.id),
        ].join(',')
      }),
    ]
    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `gyb-mensajes-${id.slice(0, 8)}-p${page + 1}.csv`
    a.click()
    URL.revokeObjectURL(url)
    toast.success('CSV descargado (solo esta página)')
  }

  const standalone = variant === 'standalone'

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 md:gap-3">
        {standalone ? (
          <Button color="light" size="sm" onClick={() => navigate('/gyb-work')}>
            <HiArrowLeft className="h-4 w-4 mr-2" /> Otra cuenta
          </Button>
        ) : (
          <Button color="light" size="sm" onClick={() => navigate(`/gyb-work/${id}`)}>
            Abrir vista GYB completa
          </Button>
        )}
        <h1 className="text-xl font-semibold">
          {standalone ? 'Mensajes GYB · carpeta de trabajo' : 'Bandeja de trabajo GYB'}
        </h1>
        <Badge color="info">{currentAccountEmail ?? id}</Badge>
        <div className="flex rounded-lg border border-slate-200 dark:border-slate-600 overflow-hidden text-sm">
          <button
            type="button"
            className={`px-3 py-1.5 ${viewMode === 'disk' ? 'bg-blue-600 text-white' : 'bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200'}`}
            onClick={() => setViewMode('disk')}
          >
            Carpetas en disco
          </button>
          <button
            type="button"
            className={`px-3 py-1.5 border-l border-slate-200 dark:border-slate-600 ${viewMode === 'labels' ? 'bg-blue-600 text-white' : 'bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200'}`}
            onClick={() => setViewMode('labels')}
          >
            Etiquetas Gmail
          </button>
        </div>
        <Button color="light" size="sm" onClick={() => setSidebarOpen((v) => !v)}>
          {sidebarOpen ? (
            <>
              <HiX className="h-4 w-4 mr-2" /> Ocultar panel
            </>
          ) : (
            <>
              <HiMenu className="h-4 w-4 mr-2" /> Mostrar panel
            </>
          )}
        </Button>
      </div>

      <p className="text-sm text-slate-500 dark:text-slate-400 max-w-3xl">
        {viewMode === 'disk' ? (
          <>
            Carpetas según el árbol de directorios del export (p. ej. fechas). Solo{' '}
            <code className="text-xs">.eml</code> en ese nivel.
          </>
        ) : (
          <>
            Etiquetas desde <code className="text-xs">msg-db.sqlite</code> (como al importar a Maildir). Requiere
            ese fichero en la carpeta de trabajo.
            {!currentHasMsgDb ? (
              <span className="text-amber-700 dark:text-amber-400">
                {' '}
                Esta cuenta no reporta msg-db en el inventario.
              </span>
            ) : null}
          </>
        )}{' '}
        El buscador cubre asunto, remitente, destinatarios (To/Cc), Message-ID, nombres de adjuntos y un extracto del
        cuerpo texto. Podés listar solo la carpeta activa o todo el export. Con etiquetas y{' '}
        <code className="text-xs">message_internaldate</code> en msg-db, el orden por fecha de correo evita leer todas las
        cabeceras cuando hay fecha en la base.
        {standalone ? (
          <>
            {' '}
            Para Dovecot/Maildir:{' '}
            <Link to={`/accounts/${id}/mailbox`} className="underline">
              visor Maildir
            </Link>
            .
          </>
        ) : (
          <>
            {' '}
            Esta vista usa el volcado GYB local (no el Maildir de Dovecot); cambiá a la pestaña “Maildir” arriba
            para ver el buzón en disco del servidor.
          </>
        )}
      </p>

      <div className="max-w-3xl space-y-3">
        <TextInput
          icon={HiSearch}
          type="search"
          placeholder="Buscar (asunto, de, para, cc, cuerpo texto, adjuntos…)"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
        />
        <div className="flex flex-wrap items-end gap-4">
          <div className="flex items-center gap-2 pb-2">
            <Checkbox
              id="gyb-list-all"
              checked={listScope === 'all'}
              onChange={(e) => setListScope(e.target.checked ? 'all' : 'folder')}
            />
            <Label htmlFor="gyb-list-all" className="cursor-pointer text-sm">
              Todo el export (todas las carpetas o etiquetas)
            </Label>
          </div>
          <div className="min-w-[12rem]">
            <Label htmlFor="gyb-sort-by" value="Ordenar por" className="mb-1" />
            <Select
              id="gyb-sort-by"
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as 'header_date' | 'mtime')}
            >
              <option value="header_date">Fecha del correo (cabecera)</option>
              <option value="mtime">Fecha del archivo en disco</option>
            </Select>
          </div>
          <div className="min-w-[11rem]">
            <Label htmlFor="gyb-sort-ord" value="Orden" className="mb-1" />
            <Select
              id="gyb-sort-ord"
              value={sortOrder}
              onChange={(e) => setSortOrder(e.target.value as 'desc' | 'asc')}
            >
              <option value="desc">Más reciente primero</option>
              <option value="asc">Más antiguo primero</option>
            </Select>
          </div>
          <Button size="xs" color="light" className="mb-0.5" onClick={downloadCurrentPageCsv} disabled={items.length === 0}>
            CSV (esta página)
          </Button>
        </div>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          Atajos con foco fuera de campos: <kbd className="px-1 rounded bg-slate-200 dark:bg-slate-700">j</kbd> /{' '}
          <kbd className="px-1 rounded bg-slate-200 dark:bg-slate-700">k</kbd> mensaje siguiente/anterior;{' '}
          <kbd className="px-1 rounded bg-slate-200 dark:bg-slate-700">r</kbd> marcar revisado (solo este navegador).
        </p>
        {listScope === 'all' ? (
          <p className="text-xs text-amber-800 dark:text-amber-200/90">
            Vista global: puede tardar en buzones muy grandes. En «Etiquetas Gmail» se usa{' '}
            <code className="text-[10px]">msg-db.sqlite</code>; sin ese archivo la API devuelve error.
          </p>
        ) : null}
      </div>

      {msgsQ.isError && (
        <Alert color="failure">
          {(msgsQ.error as Error)?.message ?? 'Error'}. Si ves <code>gyb_work_no_export</code>, esta cuenta no
          tiene export en la carpeta de trabajo.
        </Alert>
      )}

      {foldersQ.isError && (
        <Alert color="failure">{(foldersQ.error as Error)?.message ?? 'Error cargando carpetas/etiquetas'}</Alert>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        {sidebarOpen ? (
          <Card className="lg:col-span-3">
            <h2 className="text-sm font-medium mb-2">
              {viewMode === 'labels' ? 'Etiquetas Gmail' : 'Carpetas en disco'}
            </h2>
            {listScope === 'all' ? (
              <p className="text-xs text-slate-500 dark:text-slate-400 mb-2">
                Modo global: el listado no se limita a la fila seleccionada.
              </p>
            ) : null}
            {foldersQ.isLoading ? (
              <Spinner size="sm" />
            ) : folders.length === 0 ? (
              <p className="text-slate-500 text-xs">
                {viewMode === 'labels'
                  ? 'Sin etiquetas en msg-db (¿falta msg-db.sqlite o backup incompleto?). Probá “Carpetas en disco”.'
                  : 'Sin carpetas con .eml (¿solo .mbox?).'}
              </p>
            ) : (
              <ul className="space-y-1 text-sm max-h-[70vh] overflow-y-auto">
                {folders.map((f, idx) => (
                  <li key={f.id === '' ? '__root__' : `${idx}-${f.id.slice(0, 80)}`}>
                    <button
                      type="button"
                      className={`w-full text-left px-2 py-1 rounded ${
                        (viewMode === 'disk' ? folderId === f.id : labelId === f.id)
                          ? 'bg-blue-100 dark:bg-blue-900 font-medium'
                          : 'hover:bg-slate-100 dark:hover:bg-slate-800'
                      }`}
                      title={f.id || '(raíz)'}
                      onClick={() => {
                        if (viewMode === 'disk') setFolderId(f.id)
                        else setLabelId(f.id)
                        setPage(0)
                        setSelectedKey(null)
                      }}
                    >
                      {f.name}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        ) : null}

        <Card className={sidebarOpen ? 'lg:col-span-3' : 'lg:col-span-4'}>
          <div className="flex items-center justify-between mb-2 gap-2">
            <h2 className="text-sm font-medium truncate" title={selectionLabel}>
              Mensajes · {selectionLabel}
            </h2>
          </div>
          {msgsQ.isLoading ? (
            <Spinner size="sm" />
          ) : msgsQ.isError ? (
            <p className="text-red-600 text-sm">No se pudo listar</p>
          ) : items.length === 0 ? (
            <p className="text-slate-500 text-sm">
              {viewMode === 'labels' && listScope === 'folder' && !labelId
                ? 'Elegí una etiqueta en el panel.'
                : 'Sin resultados (probá otra carpeta, etiqueta o término de búsqueda).'}
            </p>
          ) : (
            <ul className="space-y-1 max-h-[70vh] overflow-y-auto text-sm" aria-label="Lista de mensajes">
              {items.map((m: MailboxMessageSummary) => (
                <li key={m.id}>
                  <button
                    type="button"
                    className={`w-full text-left px-2 py-1.5 rounded border border-transparent ${
                      selectedKey === m.id
                        ? 'bg-slate-200 dark:bg-slate-700 border-slate-300'
                        : 'hover:bg-slate-50 dark:hover:bg-slate-800'
                    }`}
                    onClick={() => setSelectedKey(m.id)}
                  >
                    <div className="flex items-start gap-1">
                      {reviewedIds.has(m.id) ? (
                        <span className="text-emerald-600 dark:text-emerald-400 shrink-0" title="Revisado">
                          ✓
                        </span>
                      ) : null}
                      <span className="font-medium line-clamp-2">{m.subject}</span>
                    </div>
                    <div className="text-xs text-slate-500 truncate">{m.from}</div>
                    <div className="text-[10px] text-slate-400">{m.date ?? ''}</div>
                    {viewMode === 'labels' && m.labels && m.labels.length > 0 ? (
                      <div className="flex flex-wrap gap-0.5 mt-1">
                        {m.labels.slice(0, 5).map((lb) => (
                          <Badge key={lb} color="gray" className="text-[9px] py-0 px-1">
                            {lb}
                          </Badge>
                        ))}
                        {m.labels.length > 5 ? (
                          <span className="text-[9px] text-slate-400">+{m.labels.length - 5}</span>
                        ) : null}
                      </div>
                    ) : null}
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className="flex flex-wrap items-center justify-between gap-2 mt-3">
            <div className="flex gap-2">
              <Button
                size="xs"
                color="light"
                disabled={page === 0}
                onClick={() => setPage((p) => Math.max(0, p - 1))}
              >
                Anterior
              </Button>
              <Button size="xs" color="light" disabled={!pageRange.hasMore} onClick={() => setPage((p) => p + 1)}>
                Siguiente
              </Button>
            </div>
            {items.length > 0 && pageRange.total != null ? (
              <span className="text-xs text-slate-500">
                {pageRange.start}–{pageRange.end} de {pageRange.total}
              </span>
            ) : items.length > 0 ? (
              <span className="text-xs text-slate-500">
                Página {page + 1}
                {pageRange.hasMore ? ' · hay más' : ''}
              </span>
            ) : null}
          </div>
        </Card>

        <Card className={sidebarOpen ? 'lg:col-span-6' : 'lg:col-span-8'}>
          <h2 className="text-sm font-medium mb-2">Contenido</h2>
          {!selectedKey ? (
            <p className="text-slate-500 text-sm">Seleccioná un mensaje</p>
          ) : bodyQ.isLoading ? (
            <Spinner />
          ) : bodyQ.isError ? (
            <p className="text-red-600 text-sm">No se pudo cargar el mensaje</p>
          ) : bodyQ.data ? (
            <div className="space-y-3 max-h-[75vh] overflow-y-auto">
              <div className="flex flex-wrap items-start gap-2">
                <div className="flex-1 min-w-0">
                  <div className="font-semibold">{bodyQ.data.subject}</div>
                  <div className="text-sm text-slate-600 dark:text-slate-300">De: {bodyQ.data.from}</div>
                  <div className="text-xs text-slate-400">{bodyQ.data.date ?? ''}</div>
                </div>
                <label className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-300 shrink-0 cursor-pointer">
                  <Checkbox
                    checked={reviewedIds.has(selectedKey)}
                    onChange={() => toggleReviewed(selectedKey)}
                  />
                  Revisado
                </label>
              </div>
              <div>
                <Label htmlFor="gyb-note" value="Nota de auditoría (local)" className="mb-1" />
                <Textarea
                  id="gyb-note"
                  rows={2}
                  value={noteDraft}
                  placeholder="Solo en este navegador…"
                  onChange={(e) => setNoteDraft(e.target.value)}
                />
                <Button
                  size="xs"
                  color="light"
                  className="mt-1"
                  onClick={() => {
                    try {
                      localStorage.setItem(noteStorageKey(id, selectedKey), noteDraft)
                      toast.success('Nota guardada en el navegador')
                    } catch {
                      toast.error('No se pudo guardar la nota')
                    }
                  }}
                >
                  Guardar nota
                </Button>
              </div>
              {(bodyQ.data.attachments ?? []).length > 0 ? (
                <div className="rounded-lg border border-slate-200 dark:border-slate-600 p-2 text-sm">
                  <div className="font-medium text-slate-700 dark:text-slate-200 mb-1">Adjuntos</div>
                  <ul className="space-y-1">
                    {(bodyQ.data.attachments ?? []).map((a) => (
                      <li
                        key={`${a.leaf_index}-${a.filename ?? a.content_type}`}
                        className="flex flex-wrap items-center gap-2"
                      >
                        <span
                          className="text-slate-600 dark:text-slate-300 truncate max-w-[60%]"
                          title={a.filename ?? undefined}
                        >
                          {a.filename ?? '(sin nombre)'}
                        </span>
                        <span className="text-xs text-slate-400">{formatBytes(a.size)}</span>
                        <Button
                          size="xs"
                          color="light"
                          onClick={() => {
                            downloadGybWorkAttachment(id, {
                              key: selectedKey,
                              leafIndex: a.leaf_index,
                              filename: a.filename,
                            }).catch(() => toast.error('No se pudo descargar el adjunto'))
                          }}
                        >
                          Descargar
                        </Button>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {bodyQ.data.text_html ? (
                <div className="border border-slate-200 dark:border-slate-700 rounded overflow-hidden bg-white dark:bg-slate-800">
                  <p className="text-xs text-slate-500 px-2 py-1 bg-slate-100 dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700">
                    Vista HTML
                  </p>
                  <iframe
                    title="html"
                    className="w-full min-h-[min(70vh,520px)] bg-white dark:bg-slate-900"
                    sandbox="allow-popups allow-downloads"
                    srcDoc={iframeSrcDoc}
                  />
                </div>
              ) : null}
              {bodyQ.data.text_plain ? (
                <details className="rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden group">
                  <summary className="cursor-pointer select-none text-sm font-medium px-3 py-2 bg-slate-50 dark:bg-slate-800 text-slate-700 dark:text-slate-200 list-none flex items-center justify-between [&::-webkit-details-marker]:hidden">
                    <span>Texto plano</span>
                    <span className="text-xs text-slate-400 group-open:hidden">Mostrar</span>
                    <span className="text-xs text-slate-400 hidden group-open:inline">Ocultar</span>
                  </summary>
                  <pre className="whitespace-pre-wrap text-sm bg-slate-50 dark:bg-slate-900 p-3 border-t border-slate-200 dark:border-slate-700 max-h-[40vh] overflow-auto m-0">
                    {bodyQ.data.text_plain}
                  </pre>
                </details>
              ) : null}
              {!bodyQ.data.text_plain && !bodyQ.data.text_html ? (
                <p className="text-slate-500 text-sm">(Sin cuerpo de texto/HTML legible)</p>
              ) : null}
            </div>
          ) : null}
        </Card>
      </div>
    </div>
  )
}
