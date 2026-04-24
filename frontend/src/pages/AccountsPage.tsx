import { useMemo, useState } from 'react'
import { Badge, Button, Card, TextInput, ToggleSwitch } from 'flowbite-react'
import { HiSearch, HiRefresh } from 'react-icons/hi'
import toast from 'react-hot-toast'
import {
  useAccounts,
  useApproveAccount,
  useRevokeAccount,
  useSyncAccounts,
} from '../api/hooks'

export default function AccountsPage() {
  const [search, setSearch] = useState('')
  const [onlyEnabled, setOnlyEnabled] = useState(false)
  const { data = [], isLoading } = useAccounts(onlyEnabled || undefined)
  const sync = useSyncAccounts()
  const approve = useApproveAccount()
  const revoke = useRevokeAccount()

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase()
    if (!term) return data
    return data.filter(
      (a) =>
        a.email.toLowerCase().includes(term) ||
        (a.full_name ?? '').toLowerCase().includes(term) ||
        (a.org_unit_path ?? '').toLowerCase().includes(term),
    )
  }, [data, search])

  async function onSync() {
    await sync.mutateAsync()
    toast.success('Sincronización con Workspace completada')
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Cuentas de Workspace</h1>
          <p className="text-slate-500">Opt-in por cuenta y provisión del vault</p>
        </div>
        <Button onClick={onSync} isProcessing={sync.isPending}>
          <HiRefresh className="h-5 w-5 mr-2" /> Sincronizar directorio
        </Button>
      </div>

      <Card>
        <div className="flex items-center gap-4 flex-wrap">
          <TextInput
            icon={HiSearch}
            placeholder="Buscar por correo, nombre o unidad organizativa"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="flex-1 min-w-[280px]"
          />
          <ToggleSwitch
            checked={onlyEnabled}
            onChange={setOnlyEnabled}
            label="Solo con backup activo"
          />
        </div>
      </Card>

      <Card>
        {isLoading ? (
          <p className="text-slate-500">Cargando…</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="text-left text-slate-500">
                <tr>
                  <th className="py-2">Correo</th>
                  <th>Nombre</th>
                  <th>OU</th>
                  <th>Estado Workspace</th>
                  <th>Backup</th>
                  <th>IMAP</th>
                  <th>Bandeja local</th>
                  <th>Último backup</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((a) => (
                  <tr key={a.id} className="border-t border-slate-100 dark:border-slate-800">
                    <td className="py-2 font-medium">{a.email}</td>
                    <td>{a.full_name ?? '—'}</td>
                    <td className="text-xs text-slate-500">{a.org_unit_path ?? '—'}</td>
                    <td>
                      <Badge
                        color={
                          a.workspace_status === 'discovered'
                            ? 'info'
                            : a.workspace_status === 'deleted_in_workspace'
                            ? 'failure'
                            : 'warning'
                        }
                      >
                        {a.workspace_status}
                      </Badge>
                    </td>
                    <td>
                      {a.is_backup_enabled ? (
                        <Badge color="success">activo</Badge>
                      ) : (
                        <Badge color="gray">inactivo</Badge>
                      )}
                    </td>
                    <td>
                      {a.imap_enabled ? (
                        <Badge color="success">sí</Badge>
                      ) : (
                        <Badge color="gray">no</Badge>
                      )}
                    </td>
                    <td className="text-xs text-slate-600 dark:text-slate-400 max-w-[10rem]">
                      {!a.maildir_on_disk
                        ? 'sin carpeta'
                        : a.maildir_user_cleared_at
                          ? 'vacía (sync Gmail)'
                          : 'en disco'}
                    </td>
                    <td className="text-xs text-slate-500">
                      {a.last_successful_backup_at ?? '—'}
                    </td>
                    <td className="space-x-2 text-right">
                      {a.is_backup_enabled ? (
                        <Button
                          size="xs"
                          color="light"
                          onClick={() =>
                            revoke.mutate(a.id, {
                              onSuccess: () => toast('Backup desactivado'),
                            })
                          }
                        >
                          Desactivar
                        </Button>
                      ) : (
                        <Button
                          size="xs"
                          onClick={() =>
                            approve.mutate(a.id, {
                              onSuccess: () => toast.success('Backup activado'),
                              onError: () => toast.error('No se pudo activar'),
                            })
                          }
                          disabled={a.workspace_status === 'deleted_in_workspace'}
                        >
                          Activar backup
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
