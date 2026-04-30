import api from './client'
import { MAILBOX_MESSAGE_TIMEOUT_MS } from './types'

export async function downloadGybWorkAttachment(
  accountId: string,
  params: { key: string; leafIndex: number; filename?: string | null },
): Promise<void> {
  const resp = await api.get<Blob>(`/accounts/${accountId}/gyb-work/attachment`, {
    params: { key: params.key, leaf_index: params.leafIndex },
    responseType: 'blob',
    timeout: MAILBOX_MESSAGE_TIMEOUT_MS,
  })
  const url = window.URL.createObjectURL(resp.data)
  try {
    const a = document.createElement('a')
    a.href = url
    a.download = (params.filename && params.filename.trim()) || 'adjunto'
    document.body.appendChild(a)
    a.click()
    a.remove()
  } finally {
    window.URL.revokeObjectURL(url)
  }
}
