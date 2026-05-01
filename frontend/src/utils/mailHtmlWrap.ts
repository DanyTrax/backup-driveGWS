/**
 * HTML de correo para iframe/srcdoc: lienzo de lectura claro y anulación de color/fondo
 * inline conflictivos (texto blanco sobre blanco, negro sobre fondo oscuro del propio HTML, etc.).
 * No sigue prefers-color-scheme: el correo se trata como documento independiente en modo claro.
 */
export function wrapMailHtmlFragment(html: string): string {
  const safe = html.replace(/<\/script/gi, '<\\/script').replace(/<\/iframe/gi, '<\\/iframe')
  const css = `
html {
  color-scheme: only light;
}
body {
  margin: 0;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  word-wrap: break-word;
  -webkit-font-smoothing: antialiased;
  background: #f8fafc !important;
  color: #0f172a !important;
}
.msa-mail-root {
  padding: 12px;
  max-width: 100%;
  box-sizing: border-box;
}
.msa-mail-root img,
.msa-mail-root video,
.msa-mail-root svg,
.msa-mail-root picture,
.msa-mail-root canvas {
  max-width: 100%;
  height: auto;
}
.msa-mail-root pre {
  white-space: pre-wrap;
}
.msa-mail-root table {
  max-width: 100%;
}
/* Pisan color/bg inline del correo (especificidad + !important) para legibilidad */
.msa-mail-root *:not(img):not(video):not(svg):not(picture):not(canvas) {
  color: inherit !important;
  background-color: transparent !important;
}
.msa-mail-root a {
  color: #1d4ed8 !important;
  text-decoration: underline !important;
}
.msa-mail-root a:visited {
  color: #6d28d9 !important;
}
.msa-mail-root mark {
  background-color: #fef08a !important;
  color: #1e293b !important;
}
`
  return `<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"/><meta http-equiv="Content-Type" content="text/html; charset=utf-8"/><base target="_blank" rel="noopener noreferrer"/><style>${css}</style></head><body><div class="msa-mail-root">${safe}</div></body></html>`
}
