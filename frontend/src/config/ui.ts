/**
 * Oculta Maildir y Webmail (menú y rutas) para el flujo Gmail → carpeta de trabajo → vault.
 * La UI completa se restaura con `VITE_HIDE_MAILDIR_WEBMAIL=false` en el build.
 */
export function hideMaildirWebmailUi(): boolean {
  return import.meta.env.VITE_HIDE_MAILDIR_WEBMAIL !== 'false'
}
