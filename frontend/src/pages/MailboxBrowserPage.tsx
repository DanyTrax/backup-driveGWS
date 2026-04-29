import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Alert, Badge, Button, Card, Spinner } from 'flowbite-react'
import { HiArrowLeft } from 'react-icons/hi'
import { useMailboxFolders, useMailboxMessage, useMailboxMessages } from '../api/hooks'

export default function MailboxBrowserPage() {
  const { accountId } = useParams<{ accountId: string }>()
  const navigate = useNavigate()
  const id = accountId ?? null
  const [folderId, setFolderId] = useState('INBOX')
  const [page, setPage] = useState(0)
  const [selectedKey, setSelectedKey] = useState<string | null>(null)

  const foldersQ = useMailboxFolders(id)
  const msgsQ = useMailboxMessages(id, folderId, page * 80)
  const bodyQ = useMailboxMessage(id, folderId, selectedKey)

  const folders = foldersQ.data ?? []
  const items = msgsQ.data?.items ?? []

  const folderLabel = useMemo(() => folders.find((f) => f.id === folderId)?.name ?? folderId, [folders, folderId])

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
      </div>

      <p className="text-sm text-slate-500 dark:text-slate-400 max-w-3xl">
        Lectura directa del Maildir en el servidor (mismos datos que importan a Dovecot). Requiere permiso{' '}
        <code className="text-xs">mailbox.view_all</code> o delegación explícita con{' '}
        <code className="text-xs">mailbox.view_delegated</code>. No sustituye Roundcube; sirve para revisar el
        respaldo desde el panel.
      </p>

      {foldersQ.isError && (
        <Alert color="failure">
          {(foldersQ.error as Error)?.message ?? 'Error cargando carpetas'}. Si ves{' '}
          <code>maildir_not_ready</code>, necesitás Maildir en disco (backup Gmail completado).
        </Alert>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        <Card className="lg:col-span-1">
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
                      folderId === f.id ? 'bg-blue-100 dark:bg-blue-900 font-medium' : 'hover:bg-slate-100 dark:hover:bg-slate-800'
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

        <Card className="lg:col-span-1">
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
            <p className="text-slate-500 text-sm">Sin mensajes en esta carpeta</p>
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

        <Card className="lg:col-span-2">
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
              {bodyQ.data.text_plain ? (
                <pre className="whitespace-pre-wrap text-sm bg-slate-50 dark:bg-slate-900 p-3 rounded border border-slate-200 dark:border-slate-700">
                  {bodyQ.data.text_plain}
                </pre>
              ) : null}
              {bodyQ.data.text_html ? (
                <div className="border border-slate-200 dark:border-slate-700 rounded overflow-hidden">
                  <p className="text-xs text-slate-500 px-2 py-1 bg-slate-100 dark:bg-slate-800">Vista HTML (sandbox)</p>
                  <iframe
                    title="html"
                    className="w-full min-h-[320px] bg-white"
                    sandbox=""
                    srcDoc={bodyQ.data.text_html}
                  />
                </div>
              ) : null}
              {!bodyQ.data.text_plain && !bodyQ.data.text_html ? (
                <p className="text-slate-500 text-sm">(Sin cuerpo de texto/HTML legible)</p>
              ) : null}
            </div>
          ) : null}
        </Card>
      </div>

      <p className="text-xs text-slate-400">
        ¿Webmail completo? <Link to="/webmail" className="underline">Webmail</Link>
      </p>
    </div>
  )
}
