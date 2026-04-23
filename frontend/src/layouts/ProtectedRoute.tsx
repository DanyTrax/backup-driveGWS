import { ReactNode, useEffect } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '../stores/auth'
import { useProfile } from '../api/hooks'

export default function ProtectedRoute({ children }: { children: ReactNode }) {
  const location = useLocation()
  const isAuth = useAuthStore((s) => s.isAuthenticated())
  const setProfile = useAuthStore((s) => s.setProfile)
  const { data, isLoading, error } = useProfile()

  useEffect(() => {
    if (data) setProfile(data)
    if (error) setProfile(null)
  }, [data, error, setProfile])

  if (!isAuth) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }
  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-slate-500">
        Cargando sesión…
      </div>
    )
  }
  return <>{children}</>
}
