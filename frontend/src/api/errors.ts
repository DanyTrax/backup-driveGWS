/** Mensaje legible desde respuestas FastAPI (detail string | object | validation array). */
export function formatApiDetail(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const parts = detail
      .map((x) =>
        typeof x === 'object' && x && 'msg' in x ? String((x as { msg: string }).msg) : '',
      )
      .filter(Boolean)
    if (parts.length) return parts.join('; ')
  }
  if (typeof detail === 'object' && detail !== null) {
    if ('message' in detail && typeof (detail as { message: unknown }).message === 'string') {
      return (detail as { message: string }).message
    }
    if ('error' in detail) {
      const err = String((detail as { error: unknown }).error)
      if (err === 'forbidden') return 'Sin permiso para esta acción.'
      return err
    }
  }
  return ''
}

export function formatVaultAssignmentError(err: unknown): string {
  const ax = err as {
    response?: { status?: number; data?: { detail?: unknown } }
    message?: string
  }
  const st = ax.response?.status
  const detail = ax.response?.data?.detail

  if (st === 403) {
    if (typeof detail === 'object' && detail !== null && 'missing' in detail) {
      const missing = (detail as { missing?: string[] }).missing
      if (missing?.length) return `Sin permiso: falta ${missing.join(', ')}.`
    }
    return 'Sin permiso (accounts.edit). Pedí acceso a un administrador.'
  }

  const text = formatApiDetail(detail)
  if (text.startsWith('vault_provision_google_failed')) {
    const code = text.match(/http_(\d+)/)?.[1] ?? '?'
    return `Google rechazó crear las carpetas (HTTP ${code}). Revisá que la SA sea Manager del pool y que BackupRoot tenga el ID correcto.`
  }
  if (text) return text

  if (!ax.response) {
    return ax.message?.includes('Network')
      ? 'Sin conexión con el servidor.'
      : 'Sin respuesta del servidor (¿contenedor app caído?). Revisá: docker compose logs app --tail 40'
  }

  return `No se pudo guardar (HTTP ${st ?? '?'}). Abrí F12 → Red → vault-assignment para ver el detalle.`
}
