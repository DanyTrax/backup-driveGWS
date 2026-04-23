import { ReactNode } from 'react'
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { Avatar, Dropdown, Sidebar } from 'flowbite-react'
import {
  HiChartPie,
  HiCog,
  HiCube,
  HiDocumentSearch,
  HiMail,
  HiOutlineLogout,
  HiRefresh,
  HiShieldCheck,
  HiUserGroup,
} from 'react-icons/hi'
import { useProfile } from '../api/hooks'
import api from '../api/client'
import { useAuthStore } from '../stores/auth'

interface NavItem {
  to: string
  label: string
  icon: ReactNode
  perm?: string
}

const NAV: NavItem[] = [
  { to: '/dashboard', label: 'Dashboard', icon: <HiChartPie className="h-5 w-5" /> },
  { to: '/accounts', label: 'Cuentas', icon: <HiUserGroup className="h-5 w-5" />, perm: 'accounts.view' },
  { to: '/tasks', label: 'Tareas de backup', icon: <HiCube className="h-5 w-5" />, perm: 'tasks.view' },
  { to: '/logs', label: 'Logs', icon: <HiDocumentSearch className="h-5 w-5" />, perm: 'logs.view' },
  { to: '/restore', label: 'Restaurar', icon: <HiRefresh className="h-5 w-5" />, perm: 'restore.view' },
  { to: '/webmail', label: 'Webmail', icon: <HiMail className="h-5 w-5" />, perm: 'webmail.sso_admin' },
  { to: '/users', label: 'Usuarios', icon: <HiShieldCheck className="h-5 w-5" />, perm: 'users.view' },
  { to: '/settings', label: 'Configuración', icon: <HiCog className="h-5 w-5" />, perm: 'settings.view' },
]

export default function AppLayout() {
  const { data: profile } = useProfile()
  const navigate = useNavigate()
  const { logout, refreshToken } = useAuthStore()

  async function handleLogout() {
    try {
      if (refreshToken) {
        await api.post('/auth/logout', { refresh_token: refreshToken })
      }
    } catch (_err) {
      // ignore
    }
    logout()
    navigate('/login', { replace: true })
  }

  const perms = new Set(profile?.permissions ?? [])

  return (
    <div className="flex min-h-screen bg-slate-50 dark:bg-slate-950">
      <Sidebar aria-label="Navegación principal" className="h-screen sticky top-0">
        <div className="flex items-center gap-2 px-2 pb-4 border-b border-slate-200 dark:border-slate-800">
          <div className="h-8 w-8 rounded-md bg-blue-600 flex items-center justify-center text-white font-bold">
            MSA
          </div>
          <span className="font-semibold text-slate-900 dark:text-white">Backup Commander</span>
        </div>
        <Sidebar.Items>
          <Sidebar.ItemGroup>
            {NAV.filter((i) => !i.perm || perms.has(i.perm)).map((item) => (
              <NavLink key={item.to} to={item.to}>
                {({ isActive }) => (
                  <Sidebar.Item icon={() => item.icon} active={isActive}>
                    {item.label}
                  </Sidebar.Item>
                )}
              </NavLink>
            ))}
          </Sidebar.ItemGroup>
        </Sidebar.Items>
      </Sidebar>
      <div className="flex-1 flex flex-col">
        <header className="h-14 flex items-center justify-between px-6 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
          <Link to="/dashboard" className="text-slate-700 dark:text-slate-200 font-medium">
            MSA Backup Commander
          </Link>
          <Dropdown
            arrowIcon={false}
            inline
            label={
              <div className="flex items-center gap-2">
                <Avatar rounded size="sm" />
                <div className="text-left hidden md:block">
                  <div className="text-sm font-medium text-slate-800 dark:text-slate-100">
                    {profile?.full_name}
                  </div>
                  <div className="text-xs text-slate-500">{profile?.role_code}</div>
                </div>
              </div>
            }
          >
            <Dropdown.Header>
              <span className="block text-sm">{profile?.email}</span>
            </Dropdown.Header>
            <Dropdown.Item onClick={() => navigate('/profile')}>Perfil</Dropdown.Item>
            <Dropdown.Divider />
            <Dropdown.Item icon={HiOutlineLogout} onClick={handleLogout}>
              Cerrar sesión
            </Dropdown.Item>
          </Dropdown>
        </header>
        <main className="flex-1 p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
