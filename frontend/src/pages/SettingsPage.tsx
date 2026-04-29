import { useEffect, useState } from 'react'
import { Button, Card, Label, Modal, TextInput } from 'flowbite-react'
import toast from 'react-hot-toast'
import { HiRefresh } from 'react-icons/hi'
import { Link } from 'react-router-dom'
import {
  useBranding,
  useBrandingConfig,
  useDeleteBrandingLogo,
  useGitRefresh,
  usePlatformBackupRun,
  useProfile,
  usePurgeAllLocalMail,
  useUpdateBranding,
  useUploadBrandingLogo,
} from '../api/hooks'
import {
  PURGE_ALL_LOCAL_MAIL_CONFIRM_PHRASE,
  brandingInitials,
  mergeBranding,
  type BrandingConfig,
} from '../api/types'

const HEX = /^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/

function BrandingSettingsForm({ config, canEdit }: { config: BrandingConfig; canEdit: boolean }) {
  const { data: publicBrand } = useBranding()
  const preview = mergeBranding(publicBrand)
  const updateBranding = useUpdateBranding()
  const uploadLogo = useUploadBrandingLogo()
  const deleteLogoFile = useDeleteBrandingLogo()

  const [appName, setAppName] = useState(config.app_name)
  const [primary, setPrimary] = useState(config.primary_color)
  const [accent, setAccent] = useState(config.accent_color)
  const [logoUrl, setLogoUrl] = useState(config.logo_url_external)
  const [logoFailPreview, setLogoFailPreview] = useState(false)

  useEffect(() => {
    setAppName(config.app_name)
    setPrimary(config.primary_color)
    setAccent(config.accent_color)
    setLogoUrl(config.logo_url_external)
  }, [config])

  useEffect(() => {
    setLogoFailPreview(false)
  }, [preview.logo_url])

  async function onSave() {
    if (!HEX.test(primary.trim()) || !HEX.test(accent.trim())) {
      toast.error('Los colores deben ser hex válidos (#RGB, #RRGGBB o #RRGGBBAA).')
      return
    }
    try {
      await updateBranding.mutateAsync({
        app_name: appName.trim() || 'MSA Backup Commander',
        primary_color: primary.trim(),
        accent_color: accent.trim(),
        logo_url: logoUrl.trim(),
      })
      toast.success('Branding guardado.')
    } catch (err: unknown) {
      const st = (err as { response?: { status?: number } })?.response?.status
      if (st === 403) {
        toast.error('Sin permiso para editar branding (settings.branding).')
      } else if (st === 422) {
        toast.error('Validación: revisá URL del logo (http(s) o ruta que empiece con /) y colores.')
      } else {
        toast.error('No se pudo guardar el branding.')
      }
    }
  }

  async function onPickFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file || !canEdit) return
    try {
      await uploadLogo.mutateAsync(file)
      toast.success('Logo subido. La URL guardada se vació para priorizar el archivo.')
    } catch (err: unknown) {
      const st = (err as { response?: { status?: number } })?.response?.status
      if (st === 403) toast.error('Sin permiso (settings.branding).')
      else if (st === 400) toast.error('Archivo no permitido o demasiado grande (máx. 2 MB).')
      else toast.error('No se pudo subir el logo.')
    }
  }

  async function onDeleteUploaded() {
    if (!canEdit) return
    try {
      await deleteLogoFile.mutateAsync()
      toast.success('Archivo de logo eliminado del servidor.')
    } catch (err: unknown) {
      const st = (err as { response?: { status?: number } })?.response?.status
      if (st === 403) toast.error('Sin permiso (settings.branding).')
      else toast.error('No se pudo eliminar el archivo.')
    }
  }

  const busy = updateBranding.isPending || uploadLogo.isPending || deleteLogoFile.isPending

  return (
    <div className="space-y-4">
      {!canEdit ? (
        <p className="text-sm text-amber-700 dark:text-amber-400">
          Solo lectura: tu rol no incluye permiso <code className="text-xs">settings.branding</code>.
        </p>
      ) : null}

      <div className="rounded-lg border border-slate-200 dark:border-slate-700 p-3 bg-slate-50/80 dark:bg-slate-900/40">
        <p className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-2">Vista previa pública</p>
        <div
          className="rounded-md p-4 flex flex-col items-center gap-2 text-center"
          style={{
            background: `linear-gradient(135deg, ${preview.primary_color}, ${preview.accent_color})`,
          }}
        >
          {preview.logo_url && !logoFailPreview ? (
            <img
              src={preview.logo_url}
              alt=""
              className="h-10 w-auto max-w-[180px] object-contain bg-white/90 rounded px-1"
              onError={() => setLogoFailPreview(true)}
            />
          ) : (
            <span
              className="inline-flex h-10 w-10 items-center justify-center rounded-md text-sm font-bold text-white"
              style={{ backgroundColor: preview.primary_color }}
            >
              {brandingInitials(preview.app_name)}
            </span>
          )}
          <span className="text-sm font-semibold text-white drop-shadow-sm">{preview.app_name}</span>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <Label htmlFor="branding-app-name" value="Nombre visible" />
          <TextInput
            id="branding-app-name"
            value={appName}
            onChange={(e) => setAppName(e.target.value)}
            disabled={!canEdit || busy}
          />
        </div>
        <div>
          <Label htmlFor="branding-primary" value="Color primario" />
          <TextInput
            id="branding-primary"
            value={primary}
            onChange={(e) => setPrimary(e.target.value)}
            disabled={!canEdit || busy}
            type="text"
          />
          <p className="mt-1 text-xs text-slate-500">Hex, ej. #1d4ed8</p>
        </div>
        <div>
          <Label htmlFor="branding-accent" value="Color acento" />
          <TextInput
            id="branding-accent"
            value={accent}
            onChange={(e) => setAccent(e.target.value)}
            disabled={!canEdit || busy}
            type="text"
          />
          <p className="mt-1 text-xs text-slate-500">Hex, ej. #0ea5e9</p>
        </div>
        <div className="sm:col-span-2">
          <Label htmlFor="branding-logo-url" value="URL del logo (opcional)" />
          <TextInput
            id="branding-logo-url"
            value={logoUrl}
            onChange={(e) => setLogoUrl(e.target.value)}
            disabled={!canEdit || busy}
            placeholder="https://… o /ruta/relativa.svg"
          />
          <p className="mt-1 text-xs text-slate-500">
            Si guardás una URL http(s) o ruta absoluta /…, se elimina un logo previamente subido como archivo.
          </p>
        </div>
      </div>

      <div className="space-y-2">
        <Label value="Logo como archivo (PNG, JPG, WebP, SVG, GIF)" />
        <input
          type="file"
          accept=".png,.jpg,.jpeg,.webp,.svg,.gif,image/png,image/jpeg,image/webp,image/svg+xml,image/gif"
          disabled={!canEdit || busy}
          onChange={(e) => void onPickFile(e)}
          className="block w-full text-sm text-slate-600 dark:text-slate-400 file:mr-3 file:rounded-lg file:border-0 file:bg-slate-200 file:px-3 file:py-2 file:text-sm file:font-medium dark:file:bg-slate-700"
        />
        {config.has_uploaded_logo ? (
          <Button size="xs" color="light" disabled={!canEdit || busy} onClick={() => void onDeleteUploaded()}>
            Quitar solo el archivo del servidor
          </Button>
        ) : (
          <p className="text-xs text-slate-500">No hay archivo de logo en disco (o ya fue reemplazado por URL).</p>
        )}
      </div>

      {canEdit ? (
        <Button color="blue" disabled={busy} isProcessing={busy} onClick={() => void onSave()}>
          Guardar branding
        </Button>
      ) : null}
    </div>
  )
}

export default function SettingsPage() {
  const { data: profile } = useProfile()
  const { data: brandingConfig, isLoading: brandingLoading } = useBrandingConfig()
  const gitRefresh = useGitRefresh()
  const platformBackup = usePlatformBackupRun()
  const purgeAllMail = usePurgeAllLocalMail()
  const perms = new Set(profile?.permissions ?? [])
  const canGitRefresh = perms.has('platform.refresh')
  const canPlatformBackup = perms.has('platform.backup')
  const canPurgeAllMail = perms.has('platform.purge_all_mail_local')
  const canBranding = perms.has('settings.branding')
  const [showPurgeModal, setShowPurgeModal] = useState(false)
  const [purgePhrase, setPurgePhrase] = useState('')

  async function onGitRefresh() {
    try {
      const r = await gitRefresh.mutateAsync()
      if (r.error === 'not_a_git_repository' && r.hint) {
        toast.error(r.hint, { duration: 14_000 })
        return
      }
      if (r.ok) {
        const short = r.head ? `${r.head.slice(0, 7)}` : '—'
        toast.success(`Repositorio actualizado (fetch, checkout, reset). HEAD ${short}`)
      } else {
        const last = r.steps?.filter((s) => s.rc !== 0).pop() ?? r.steps?.[r.steps.length - 1]
        const hint = [last?.stderr, last?.stdout].filter(Boolean).join('\n').trim()
        toast.error(hint ? `Git refresh falló:\n${hint.slice(0, 500)}` : 'Git refresh falló (revisá logs del contenedor).')
      }
    } catch (err: unknown) {
      const st = (err as { response?: { status?: number } })?.response?.status
      if (st === 403) {
        toast.error('No tenés permiso para Git refresh (hace falta platform.refresh).')
      } else {
        toast.error('No se pudo ejecutar Git refresh.')
      }
    }
  }

  async function onPlatformBackup() {
    try {
      const r = await platformBackup.mutateAsync()
      if (r.ok) {
        toast.success(`Backup de plataforma subido: ${r.filename ?? 'archivo .age'}`)
      } else {
        const code = r.error ?? 'error_desconocido'
        const reason = (r as { reason?: string }).reason ?? ''
        const msg =
          code === 'platform_backup_exception' && reason
            ? `Backup de plataforma: ${reason.slice(0, 400)}`
            : code === 'age_recipient_not_configured'
              ? 'Falta configurar el destinatario age (PLATFORM_BACKUP_AGE_RECIPIENT) en el servidor.'
              : code === 'age_recipient_invalid'
                ? reason ||
                  'PLATFORM_BACKUP_AGE_RECIPIENT debe ser una clave pública age1… (no el texto del comentario del .env).'
              : code === 'vault_root_missing'
                ? 'Falta vault de Drive configurado.'
                : reason
                  ? `${code}: ${reason.slice(0, 300)}`
                  : `No se pudo generar el backup (${code}).`
        toast.error(msg)
      }
    } catch (err: unknown) {
      const st = (err as { response?: { status?: number } })?.response?.status
      if (st === 403) {
        toast.error('No tenés permiso para backup de plataforma (platform.backup).')
      } else {
        toast.error('No se pudo ejecutar el backup de plataforma.')
      }
    }
  }

  async function onConfirmPurgeAll() {
    if (purgePhrase.trim() !== PURGE_ALL_LOCAL_MAIL_CONFIRM_PHRASE) {
      toast.error('La frase de confirmación no coincide.')
      return
    }
    try {
      const r = await purgeAllMail.mutateAsync(purgePhrase.trim())
      toast.success(
        `Operación completada: ${r.workspace_accounts} cuentas, Maildirs ${r.maildirs_cleared}, GYB ${r.gyb_workdirs_cleared}, logs Gmail eliminados ${r.gmail_backup_logs_deleted}, tokens webmail ${r.webmail_tokens_deleted}.`,
      )
      setShowPurgeModal(false)
      setPurgePhrase('')
    } catch (err: unknown) {
      const ax = err as { response?: { status?: number; data?: { detail?: string } } }
      if (ax.response?.status === 403) {
        toast.error('Sin permiso (platform.purge_all_mail_local).')
      } else if (ax.response?.data?.detail === 'invalid_confirmation') {
        toast.error('Frase inválida.')
      } else {
        toast.error('No se pudo completar la purga global.')
      }
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Configuración</h1>
        <p className="text-slate-500">Integraciones, branding y operación</p>
      </div>
      <p className="text-xs text-slate-400">
        Compilación de esta interfaz:{' '}
        <code className="bg-slate-100 dark:bg-slate-800 px-1 rounded">{import.meta.env.VITE_UI_BUILD_ID}</code>
        . Si los mensajes de error no coinciden con lo esperado o ves textos “viejos”, recargá sin caché
        (Ctrl+Shift+R o Cmd+Shift+R) o reconstruí la imagen Docker del frontend.
      </p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <h2 className="font-semibold">Asistente inicial</h2>
          <p className="text-sm text-slate-500">
            Si necesitas rehacer la configuración de Google Workspace puedes volver al wizard.
          </p>
          <Link className="text-blue-600 font-medium" to="/setup">
            Abrir asistente
          </Link>
        </Card>
        <Card>
          <h2 className="font-semibold">Notificaciones</h2>
          <p className="text-sm text-slate-500">
            Conecta Telegram, Discord y Gmail. Define matrices por categoría.
          </p>
        </Card>
        <Card className="md:col-span-2">
          <h2 className="font-semibold">Branding</h2>
          <p className="text-sm text-slate-500 mb-4">
            Cambia logo, colores y nombre visible de la plataforma (login, título del navegador y cabecera del panel).
          </p>
          {brandingLoading || !brandingConfig ? (
            <p className="text-sm text-slate-500">Cargando configuración…</p>
          ) : (
            <BrandingSettingsForm config={brandingConfig} canEdit={canBranding} />
          )}
        </Card>
        <Card>
          <h2 className="font-semibold mb-2">Git y respaldo de plataforma</h2>
          <p className="text-sm text-slate-500 mb-4">
            <strong>En VPS con imagen Docker</strong> el código en <code className="text-xs">/app</code> no trae carpeta{' '}
            <code className="text-xs">.git</code>: ahí tenés que actualizar con{' '}
            <code className="text-xs">git pull</code> en el host (<code className="text-xs">/opt/stacks/backup-stack</code>) y{' '}
            <code className="text-xs">docker compose up -d --build</code> desde <code className="text-xs">docker/</code>.
            El botón solo sirve si montás un repo con <code className="text-xs">.git</code> y configurás{' '}
            <code className="text-xs">GIT_WORKING_TREE</code> en <code className="text-xs">.env</code>.
          </p>
          <div className="flex flex-wrap gap-2">
            {canGitRefresh ? (
              <Button
                color="blue"
                onClick={() => void onGitRefresh()}
                disabled={gitRefresh.isPending}
                isProcessing={gitRefresh.isPending}
              >
                <HiRefresh className="h-4 w-4 mr-2" />
                Actualizar repositorio (Git refresh)
              </Button>
            ) : (
              <p className="text-sm text-amber-700 dark:text-amber-400">
                Tu rol no incluye permiso <code className="text-xs">platform.refresh</code>.
              </p>
            )}
            {canPlatformBackup ? (
              <Button
                color="light"
                onClick={() => void onPlatformBackup()}
                disabled={platformBackup.isPending}
                isProcessing={platformBackup.isPending}
              >
                Backup cifrado de plataforma
              </Button>
            ) : null}
          </div>
        </Card>
        <Card className="md:col-span-2 border-red-200 dark:border-red-900/50">
          <h2 className="font-semibold text-red-800 dark:text-red-300">Copias locales de correo (plataforma)</h2>
          <p className="text-sm text-slate-600 dark:text-slate-400 mt-1 mb-3">
            Vacía Maildir y carpetas de trabajo GYB en disco para <strong>todas</strong> las cuentas Workspace, elimina
            filas de <code className="text-xs">backup_logs</code> con alcance Gmail y borra tokens de webmail. No elimina
            usuarios del panel (<code className="text-xs">sys_users</code>) ni filas <code className="text-xs">gw_accounts</code>.
            No borra correo en Gmail ni archivos en Drive. Para elegir qué borrar en una sola cuenta usá{' '}
            <Link className="text-blue-600 font-medium" to="/accounts">
              Cuentas → Datos locales
            </Link>
            .
          </p>
          {canPurgeAllMail ? (
            <Button color="failure" onClick={() => setShowPurgeModal(true)}>
              Eliminar todas las copias locales de correo…
            </Button>
          ) : (
            <p className="text-sm text-amber-700 dark:text-amber-400">
              Solo super administrador: permiso <code className="text-xs">platform.purge_all_mail_local</code>.
            </p>
          )}
        </Card>
      </div>

      <Modal show={showPurgeModal} onClose={() => { setShowPurgeModal(false); setPurgePhrase('') }} size="lg">
        <Modal.Header>Confirmar purga global de correo local</Modal.Header>
        <Modal.Body className="space-y-4">
          <p className="text-sm text-slate-600 dark:text-slate-400">
            Esta acción afecta a todas las cuentas Workspace. Copiá y pegá la frase exacta en el campo inferior:
          </p>
          <pre className="text-xs bg-slate-100 dark:bg-slate-900 p-3 rounded overflow-x-auto select-all">
            {PURGE_ALL_LOCAL_MAIL_CONFIRM_PHRASE}
          </pre>
          <TextInput
            placeholder="Frase de confirmación"
            value={purgePhrase}
            onChange={(e) => setPurgePhrase(e.target.value)}
            autoComplete="off"
          />
        </Modal.Body>
        <Modal.Footer>
          <Button color="light" onClick={() => { setShowPurgeModal(false); setPurgePhrase('') }}>
            Cancelar
          </Button>
          <Button
            color="failure"
            disabled={purgeAllMail.isPending}
            isProcessing={purgeAllMail.isPending}
            onClick={() => void onConfirmPurgeAll()}
          >
            Confirmar eliminación
          </Button>
        </Modal.Footer>
      </Modal>
    </div>
  )
}
