import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Alert, Badge, Button, Card, Label, Select, Spinner, TextInput } from 'flowbite-react'
import toast from 'react-hot-toast'
import { HiArrowLeft, HiDownload, HiMenu, HiSearch, HiX } from 'react-icons/hi'
import GybWorkAccountViewer from '../components/GybWorkAccountViewer'
import { downloadMaildirExportZip, maildirExportErrorMessage } from '../api/maildirExport'
import { downloadMailboxAttachment } from '../api/mailboxAttachment'
import { useMailboxFolders, useMailboxMessage, useMailboxMessages } from '../api/hooks'

type ViewerTab = 'maildir' | 'gyb'

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

export default function MailboxBrowserPage() {
  const { accountId } = useParams<{ accountId: string }>()
  const navigate = useNavigate()
  const id = accountId ?? null
  const [viewerTab, setViewerTab] = useState<ViewerTab>('maildir')
  const [folderId, setFolderId] = useState('INBOX')
  const [page, setPage] = useState(0)
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const [exporting, setExporting] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [maildirSearchInput, setMaildirSearchInput] = useState('')
  const [maildirSearchQ, setMaildirSearchQ] = useState('')
  const [maildirSort, setMaildirSort] = useState<'mtime' | 'header_date'>('mtime')

  useEffect(() => {
    const t = window.setTimeout(() => setMaildirSearchQ(maildirSearchInput.trim()), 400)
    return () => window.clearTimeout(t)
  }, [maildirSearchInput])

  useEffect(() => {
    setPage(0)
    setSelectedKey(null)
  }, [maildirSearchQ, folderId, maildirSort])

  const foldersQ = useMailboxFolders(id)
  const msgsQ = useMailboxMessages(id, folderId, page * 80, { q: maildirSearchQ, sortBy: maildirSort })
  const bodyQ = useMailboxMessage(id, folderId, selectedKey)

  const folders = foldersQ.data ?? []
  const items = msgsQ.data?.items ?? []

  const folderLabel = useMemo(() => folders.find((f) => f.id === folderId)?.name ?? folderId, [folders, folderId])

  const iframeSrcDoc = useMemo(
    () => (bodyQ.data?.text_html ? wrapMailHtmlFragment(bodyQ.data.text_html) : ''),
    [bodyQ.data?.text_html],
  )

  if (!id) {
    return <Alert color="failure">Falta id de cuenta</Alert>
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Button color="light" size="sm" onClick={() => navigate('/accounts')}>
          <HiArrowLeft className="h-4 w-4 mr-2" /> Cuentas
        </Button>
        <h1 className="text-xl font-semibold">Correo en Maildir (backup local)</h1>
        <Badge color="info">Cuenta {id}</Badge>
        <div className="flex rounded-lg border border-slate-200 dark:border-slate-600 overflow-hidden text-sm">
          <button
            type="button"
            className={`px-3 py-1.5 ${
              viewerTab === 'maildir'
                ? 'bg-blue-600 text-white'
                : 'bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200'
            }`}
            onClick={() => setViewerTab('maildir')}
          >
            Maildir (Dovecot)
          </button>
          <button
            type="button"
            className={`px-3 py-1.5 border-l border-slate-200 dark:border-slate-600 ${
              viewerTab === 'gyb'
                ? 'bg-blue-600 text-white'
                : 'bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200'
            }`}
            onClick={() => setViewerTab('gyb')}
          >
            Bandeja trabajo GYB
          </button>
        </div>
        <Button
          color="light"
          size="sm"
          disabled={exporting || foldersQ.isError}
          isProcessing={exporting}
          onClick={() => {
            if (!id) return
            setExporting(true)
            downloadMaildirExportZip(id)
              .then(() => toast.success('Descarga iniciada (ZIP del Maildir).'))
              .catch((e) => toast.error(maildirExportErrorMessage(e)))
              .finally(() => setExporting(false))
          }}
        >
          <HiDownload className="h-4 w-4 mr-2" />
          Exportar Maildir (.zip)
        </Button>
        {viewerTab === 'maildir' ? (
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
        ) : null}
      </div>

      <p className="text-sm text-slate-500 dark:text-slate-400 max-w-3xl">
        {viewerTab === 'maildir' ? (
          <>
            Lectura directa del Maildir en el servidor (mismos datos que importan a Dovecot). Requiere permiso{' '}
            <code className="text-xs">mailbox.view_all</code> o delegación explícita con{' '}
            <code className="text-xs">mailbox.view_delegated</code>.{' '}
            <strong>Exportar ZIP</strong> genera la estructura Maildir tal como está en disco. Orden por defecto: más
            reciente primero según la <strong>fecha del fichero</strong> en disco; podés cambiar a la cabecera{' '}
            <code className="text-xs">Date</code> del mensaje (puede ser más lento en carpetas muy grandes).
          </>
        ) : (
          <>
            Volcado local GYB (<code className="text-xs">.eml</code> en carpeta de trabajo), distinto del Maildir de
            Dovecot. Volvé a la pestaña Maildir para ver el buzón en disco del servidor.
          </>
        )}
      </p>

      {viewerTab === 'maildir' ? (
        <>
          <div className="flex flex-wrap gap-4 items-end max-w-4xl">
            <div className="flex-1 min-w-[220px]">
              <Label htmlFor="maildir-q" value="Buscar en asunto o remitente" className="mb-1" />
              <TextInput
                id="maildir-q"
                icon={HiSearch}
                type="search"
                placeholder="Escribí y esperá un momento…"
                value={maildirSearchInput}
                onChange={(e) => setMaildirSearchInput(e.target.value)}
              />
            </div>
            <div className="min-w-[240px]">
              <Label htmlFor="maildir-sort" value="Ordenar por" className="mb-1" />
              <Select
                id="maildir-sort"
                value={maildirSort}
                onChange={(e) => setMaildirSort(e.target.value as 'mtime' | 'header_date')}
              >
                <option value="mtime">Más reciente (fecha de fichero)</option>
                <option value="header_date">Fecha cabecera Date</option>
              </Select>
            </div>
          </div>

          {foldersQ.isError && (
            <Alert color="failure">
              {(foldersQ.error as Error)?.message ?? 'Error cargando carpetas'}. Si ves{' '}
              <code>maildir_not_ready</code>, necesitás Maildir en disco (backup Gmail completado).
            </Alert>
          )}

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
            {sidebarOpen ? (
              <Card className="lg:col-span-3">
                <h2 className="text-sm font-medium mb-2">Carpetas</h2>
                {foldersQ.isLoading ? (
                  <Spinner size="sm" />
                ) : (
                  <ul className="space-y-1 text-sm">
                    {folders.map((f) => (
                      <li key={f.id}>
                        <button
                          type="button"
                          className={`w-full text-left px-2 py-1 rounded ${
                            folderId === f.id
                              ? 'bg-blue-100 dark:bg-blue-900 font-medium'
                              : 'hover:bg-slate-100 dark:hover:bg-slate-800'
                          }`}
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
                <p className="text-red-600 text-sm">Error listando mensajes</p>
              ) : items.length === 0 ? (
                <p className="text-slate-500 text-sm">
                  Sin mensajes en esta carpeta (o ninguno coincide con la búsqueda).
                </p>
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
                              disabled={!id}
                              onClick={() => {
                                if (!id || !selectedKey) return
                                downloadMailboxAttachment(id, {
                                  folder: folderId,
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
                        Vista HTML (sin scripts; imágenes incrustadas vía servidor cuando es posible)
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
        </>
      ) : (
        <GybWorkAccountViewer accountId={id} variant="embedded" />
      )}

      <p className="text-xs text-slate-400">
        ¿Webmail completo? <Link to="/webmail" className="underline">Webmail</Link>
      </p>
    </div>
  )
}
