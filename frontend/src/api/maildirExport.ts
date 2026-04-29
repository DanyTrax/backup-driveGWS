import api from './client'

const EXPORT_TIMEOUT_MS = 3_600_000 // 1 h — buzones muy grandes

/** Descarga el ZIP del Maildir local (mismo permiso que el visor Maildir). */
export async function downloadMaildirExportZip(accountId: string): Promise<void> {
  const r = await api.get<Blob>(`/accounts/${accountId}/mailbox/maildir-export.zip`, {
    responseType: 'blob',
    timeout: EXPORT_TIMEOUT_MS,
  })

  let filename = `maildir_${accountId.slice(0, 8)}.zip`
  const cd = r.headers['content-disposition']
  if (cd && typeof cd === 'string') {
    const m = /filename\*=UTF-8''([^;\s]+)|filename="([^"]+)"/i.exec(cd)
    const raw = decodeURIComponent(m?.[1] || m?.[2] || '')
    if (raw) filename = raw
  }

  const url = URL.createObjectURL(r.data)
  try {
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.rel = 'noopener'
    document.body.appendChild(a)
    a.click()
    a.remove()
  } finally {
    URL.revokeObjectURL(url)
  }
}

export function maildirExportErrorMessage(err: unknown): string {
  const ax = err as { response?: { status?: number; data?: Blob | unknown } }
  const st = ax.response?.status
  if (st === 403) return 'Sin permiso para exportar este buzón (mailbox.view_* / delegación).'
  if (st === 409) return 'Maildir no disponible (vacío o sin layout cur/new/tmp).'
  if (st === 413) return 'El buzón supera el límite configurado (MAILDIR_EXPORT_MAX_BYTES).'
  if (st === 401) return 'Sesión expirada; iniciá sesión de nuevo.'
  return 'No se pudo generar la descarga.'
}
