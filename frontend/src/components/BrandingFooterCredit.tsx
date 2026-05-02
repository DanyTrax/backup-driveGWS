import type { BrandingPublic } from '../api/types'

type Props = {
  brand: BrandingPublic
  className?: string
  linkClassName?: string
}

/** Crédito «por …» en el pie cuando hay texto y URL en branding. */
export function BrandingFooterCredit({ brand, className = '', linkClassName = '' }: Props) {
  const label = (brand.footer_by_label || '').trim()
  const url = (brand.footer_by_url || '').trim()
  if (!label || !url) return null
  const external = url.startsWith('http://') || url.startsWith('https://')
  return (
    <p className={className}>
      <a
        href={url}
        className={linkClassName}
        target={external ? '_blank' : undefined}
        rel={external ? 'noopener noreferrer' : undefined}
      >
        {label}
      </a>
    </p>
  )
}
