/** Fecha legible para tablas y detalle de logs: DD-MM-YYYY h:mm am/pm (zona horaria local). */

export function formatLogDateTime(value: string | null | undefined): string {
  if (value == null || String(value).trim() === '') return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return String(value)

  const day = String(d.getDate()).padStart(2, '0')
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const year = d.getFullYear()

  let h24 = d.getHours()
  const min = String(d.getMinutes()).padStart(2, '0')
  const ampm = h24 >= 12 ? 'pm' : 'am'
  let h12 = h24 % 12
  if (h12 === 0) h12 = 12

  return `${day}-${month}-${year} ${h12}:${min} ${ampm}`
}
