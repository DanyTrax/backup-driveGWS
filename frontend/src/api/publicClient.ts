import axios from 'axios'

/**
 * Llamadas sin Bearer ni reintento de refresh (asignar clave webmail, health público, etc.)
 * Así el usuario puede tener sesión de admin y el enlace de token no hereda 401/refresh.
 */
const publicClient = axios.create({
  baseURL: '/api',
  timeout: 30_000,
})

export default publicClient
