import axios, { AxiosError, type AxiosRequestConfig } from 'axios'
import { useAuthStore } from '../stores/auth'

const api = axios.create({
  baseURL: '/api',
  timeout: 30_000,
})

let refreshPromise: Promise<string> | null = null

async function refreshAccess(): Promise<string> {
  const { refreshToken, setTokens, logout } = useAuthStore.getState()
  if (!refreshToken) {
    logout()
    throw new Error('no_refresh_token')
  }
  try {
    const resp = await axios.post('/api/auth/refresh', { refresh_token: refreshToken })
    setTokens(resp.data.access_token, resp.data.refresh_token, resp.data.expires_in)
    return resp.data.access_token as string
  } catch (err) {
    logout()
    throw err
  }
}

api.interceptors.request.use((config) => {
  const { accessToken } = useAuthStore.getState()
  if (accessToken) {
    config.headers = config.headers ?? {}
    config.headers['Authorization'] = `Bearer ${accessToken}`
  }
  return config
})

api.interceptors.response.use(
  (resp) => resp,
  async (error: AxiosError) => {
    const original = error.config as AxiosRequestConfig & { _retry?: boolean }
    if (error.response?.status === 401 && !original?._retry) {
      // No intentar refresh en el propio login: acaba en logout+throw sin `response` y el panel muestra
      // "Revisá correo y contraseña" aunque el backend haya devuelto invalid_credentials.
      const path = String(original?.url ?? '')
      if (path.includes('/auth/login')) {
        return Promise.reject(error)
      }
      const detail = (error.response.data as { detail?: { error?: string } })?.detail
      if (detail?.error === 'mfa_required') {
        return Promise.reject(error)
      }
      if (!original) return Promise.reject(error)
      original._retry = true
      if (!refreshPromise) refreshPromise = refreshAccess().finally(() => (refreshPromise = null))
      try {
        const token = await refreshPromise
        original.headers = original.headers ?? {}
        ;(original.headers as Record<string, string>)['Authorization'] = `Bearer ${token}`
        return api(original)
      } catch (e) {
        return Promise.reject(e)
      }
    }
    return Promise.reject(error)
  },
)

export default api
