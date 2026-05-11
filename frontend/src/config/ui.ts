/**
 * Oculta Maildir y Webmail (menú y rutas) para el flujo Gmail → carpeta de trabajo → vault.
 * La UI completa se restaura con `VITE_HIDE_MAILDIR_WEBMAIL=false` en el build.
 */
export function hideMaildirWebmailUi(): boolean {
  return import.meta.env.VITE_HIDE_MAILDIR_WEBMAIL !== 'false'
}

/**
 * Oculta el visor «GYB en Drive» (1-GMAIL/gyb_mbox vía rclone). Las rutas API no se eliminan.
 * Para volver a mostrar el ítem de menú, enlaces y la ruta `/gyb-vault-work`: `VITE_HIDE_GYB_VAULT_DRIVE=false`
 */
export function hideGybVaultDriveUi(): boolean {
  return import.meta.env.VITE_HIDE_GYB_VAULT_DRIVE !== 'false'
}
