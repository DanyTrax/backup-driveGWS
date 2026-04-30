import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Alert, Badge, Button, Card, Spinner } from 'flowbite-react'
import toast from 'react-hot-toast'
import { HiArrowLeft, HiMenu, HiX } from 'react-icons/hi'
import { downloadGybWorkAttachment } from '../api/gybWorkAttachment'
import { useGybWorkAccounts, useGybWorkFolders, useGybWorkMessage, useGybWorkMessages } from '../api/hooks'

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

function wrapMailHtmlFragment(html: string): string {
  const safe = html.replace(/<\/script/gi, '<\\/script').replace(/<\/iframe/gi, '<\\/iframe')
  return `<!DOCTYPE html><html><head><meta charset="utf-8"/><base target="_blank" rel="noopener noreferrer"/><style>
body{font-family:system-ui,-apple-system,sans-serif;margin:0;padding:12px;word-wrap:break-word;color:rgb(30 41 59);}
@media (prefers-color-scheme:dark){body{color:rgb(226 232 240);background:#0f172a;}}
img,video{max-width:100%;height:auto;}pre{white-space:pre-wrap;}table{max-width:100%;}
</style></head><body>${safe}</body></html>`
}

export default function GybWorkBrowserPage() {
  const { accountId } = useParams<{ accountId?: string }>()
  const navigate = useNavigate()
  const id = accountId ?? null
  const [folderId, setFolderId] = useState('')
  const [page, setPage] = useState(0)
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(true)

  const accountsQ = useGybWorkAccounts()
  const foldersQ = useGybWorkFolders(id)
  const msgsQ = useGybWorkMessages(id, folderId, page * 80)
  const bodyQ = useGybWorkMessage(id, selectedKey)

  const accounts = accountsQ.data ?? []
  const folders = foldersQ.data ?? []
  const items = msgsQ.data?.items ?? []

  const folderLabel = useMemo(
    () => folders.find((f) => f.id === folderId)?.name ?? (folderId ? folderId : '(raíz)'),
    [folders, folderId],
  )

  const iframeSrcDoc = useMemo(
    () => (bodyQ.data?.text_html ? wrapMailHtmlFragment(bodyQ.data.text_html) : ''),
    [bodyQ.data?.text_html],
  )

  const currentAccountEmail = useMemo(() => accounts.find((a) => a.id === id)?.email, [accounts, id])

  useEffect(() => {
    if (!foldersQ.data?.length) return
    setFolderId((prev) =>
      foldersQ.data!.some((f) => f.id === prev) ? prev : (foldersQ.data![0]?.id ?? ''),
    )
  }, [foldersQ.data])

  useEffect(() => {
    setPage(0)
    setSelectedKey(null)
  }, [id, folderId])

  if (!id) {
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

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Button color="light" size="sm" onClick={() => navigate('/gyb-work')}>
          <HiArrowLeft className="h-4 w-4 mr-2" /> Otra cuenta
        </Button>
        <h1 className="text-xl font-semibold">Mensajes GYB · carpeta de trabajo</h1>
        <Badge color="info">{currentAccountEmail ?? id}</Badge>
        <Button color="light" size="sm" onClick={() => setSidebarOpen((v) => !v)}>
          {sidebarOpen ? (
            <>
              <HiX className="h-4 w-4 mr-2" /> Ocultar carpetas
            </>
          ) : (
            <>
              <HiMenu className="h-4 w-4 mr-2" /> Mostrar carpetas
            </>
          )}
        </Button>
      </div>

      <p className="text-sm text-slate-500 dark:text-slate-400 max-w-3xl">
        Las carpetas coinciden con los directorios bajo el trabajo GYB donde hay ficheros{' '}
        <code className="text-xs">.eml</code> (etiquetas/rutas que crea la exportación). En cada carpeta solo se listan
        los mensajes de ese nivel (no subcarpetas). Para Maildir/Dovecot usá el{' '}
        <Link to={`/accounts/${id}/mailbox`} className="underline">
          visor Maildir
        </Link>
        .
      </p>

      {msgsQ.isError && (
        <Alert color="failure">
          {(msgsQ.error as Error)?.message ?? 'Error'}. Si ves <code>gyb_work_no_export</code>, esta cuenta no tiene
          export en la carpeta de trabajo.
        </Alert>
      )}

      {foldersQ.isError && (
        <Alert color="failure">{(foldersQ.error as Error)?.message ?? 'Error cargando carpetas'}</Alert>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        {sidebarOpen ? (
          <Card className="lg:col-span-3">
            <h2 className="text-sm font-medium mb-2">Carpetas (work GYB)</h2>
            {foldersQ.isLoading ? (
              <Spinner size="sm" />
            ) : folders.length === 0 ? (
              <p className="text-slate-500 text-xs">Sin carpetas con .eml (¿solo .mbox?)</p>
            ) : (
              <ul className="space-y-1 text-sm max-h-[70vh] overflow-y-auto">
                {folders.map((f) => (
                  <li key={f.id === '' ? '__root__' : f.id}>
                    <button
                      type="button"
                      className={`w-full text-left px-2 py-1 rounded ${
                        folderId === f.id ? 'bg-blue-100 dark:bg-blue-900 font-medium' : 'hover:bg-slate-100 dark:hover:bg-slate-800'
                      }`}
                      title={f.id || '(raíz)'}
                      onClick={() => {
                        setFolderId(f.id)
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
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-sm font-medium truncate" title={folderLabel}>
              Mensajes · {folderLabel}
            </h2>
          </div>
          {msgsQ.isLoading ? (
            <Spinner size="sm" />
          ) : msgsQ.isError ? (
            <p className="text-red-600 text-sm">No se pudo listar</p>
          ) : items.length === 0 ? (
            <p className="text-slate-500 text-sm">No hay ficheros .eml visibles (puede haber solo .mbox).</p>
          ) : (
            <ul className="space-y-1 max-h-[70vh] overflow-y-auto text-sm">
              {items.map((m) => (
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
                    <div className="font-medium line-clamp-2">{m.subject}</div>
                    <div className="text-xs text-slate-500 truncate">{m.from}</div>
                    <div className="text-[10px] text-slate-400">{m.date ?? ''}</div>
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className="flex gap-2 mt-3">
            <Button
              size="xs"
              color="light"
              disabled={page === 0}
              onClick={() => setPage((p) => Math.max(0, p - 1))}
            >
              Anterior
            </Button>
            <Button size="xs" color="light" disabled={items.length < 80} onClick={() => setPage((p) => p + 1)}>
              Siguiente
            </Button>
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
              <div>
                <div className="font-semibold">{bodyQ.data.subject}</div>
                <div className="text-sm text-slate-600 dark:text-slate-300">De: {bodyQ.data.from}</div>
                <div className="text-xs text-slate-400">{bodyQ.data.date ?? ''}</div>
              </div>
              {(bodyQ.data.attachments ?? []).length > 0 ? (
                <div className="rounded-lg border border-slate-200 dark:border-slate-600 p-2 text-sm">
                  <div className="font-medium text-slate-700 dark:text-slate-200 mb-1">Adjuntos</div>
                  <ul className="space-y-1">
                    {(bodyQ.data.attachments ?? []).map((a) => (
                      <li key={`${a.leaf_index}-${a.filename ?? a.content_type}`} className="flex flex-wrap items-center gap-2">
                        <span className="text-slate-600 dark:text-slate-300 truncate max-w-[60%]" title={a.filename ?? undefined}>
                          {a.filename ?? '(sin nombre)'}
                        </span>
                        <span className="text-xs text-slate-400">{formatBytes(a.size)}</span>
                        <Button
                          size="xs"
                          color="light"
                          disabled={!id}
                          onClick={() => {
                            if (!id || !selectedKey) return
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
