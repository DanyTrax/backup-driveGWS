import { ReactNode, useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { Avatar, Dropdown } from 'flowbite-react'
import clsx from 'clsx'
import {
  HiChartPie,
  HiCog,
  HiCube,
  HiDocumentSearch,
  HiMail,
  HiMenu,
  HiOutlineLogout,
  HiRefresh,
  HiShieldCheck,
  HiUserGroup,
} from 'react-icons/hi'
import { useBranding, useProfile } from '../api/hooks'
import api from '../api/client'
import { useAuthStore } from '../stores/auth'
import { brandingInitials, mergeBranding } from '../api/types'

const SIDEBAR_STORAGE_KEY = 'msa-sidebar-expanded'

interface NavItem {
  to: string
  label: string
  icon: ReactNode
  perm?: string
}

const NAV: NavItem[] = [
  { to: '/dashboard', label: 'Dashboard', icon: <HiChartPie className="h-5 w-5 shrink-0" /> },
  { to: '/accounts', label: 'Cuentas', icon: <HiUserGroup className="h-5 w-5 shrink-0" />, perm: 'accounts.view' },
  { to: '/tasks', label: 'Tareas de backup', icon: <HiCube className="h-5 w-5 shrink-0" />, perm: 'tasks.view' },
  { to: '/logs', label: 'Logs', icon: <HiDocumentSearch className="h-5 w-5 shrink-0" />, perm: 'logs.view' },
  { to: '/restore', label: 'Restaurar', icon: <HiRefresh className="h-5 w-5 shrink-0" />, perm: 'restore.view' },
  { to: '/webmail', label: 'Webmail', icon: <HiMail className="h-5 w-5 shrink-0" />, perm: 'webmail.sso_admin' },
  { to: '/users', label: 'Usuarios', icon: <HiShieldCheck className="h-5 w-5 shrink-0" />, perm: 'users.view' },
  { to: '/settings', label: 'Configuración', icon: <HiCog className="h-5 w-5 shrink-0" />, perm: 'settings.view' },
]

function readSidebarExpanded(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

export default function AppLayout() {
  const { data: profile } = useProfile()
  const { data: brandRaw } = useBranding()
  const brand = mergeBranding(brandRaw)
  const navigate = useNavigate()
  const { logout, refreshToken } = useAuthStore()
  const [sidebarExpanded, setSidebarExpanded] = useState(readSidebarExpanded)
  const [brandLogoFailed, setBrandLogoFailed] = useState(false)

  useEffect(() => {
    document.title = brand.app_name
  }, [brand.app_name])

  useEffect(() => {
    setBrandLogoFailed(false)
  }, [brand.logo_url])

  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_STORAGE_KEY, sidebarExpanded ? '1' : '0')
    } catch {
      /* ignore */
    }
  }, [sidebarExpanded])

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
  const visibleNav = NAV.filter((i) => !i.perm || perms.has(i.perm))
  const showHeaderLogo = Boolean(brand.logo_url && !brandLogoFailed)

  return (
    <div className="flex min-h-screen bg-slate-50 dark:bg-slate-950">
      <aside
        aria-label="Navegación principal"
        className={clsx(
          'flex flex-col h-screen sticky top-0 z-30 shrink-0 border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 transition-[width] duration-200 ease-out',
          sidebarExpanded ? 'w-60' : 'w-[4.25rem]',
        )}
      >
        <div
          className={clsx(
            'flex items-center gap-2 border-b border-slate-200 dark:border-slate-800 min-h-[3.25rem]',
            sidebarExpanded ? 'px-3 py-2' : 'px-2 py-2 justify-center flex-col gap-1',
          )}
        >
          <button
            type="button"
            onClick={() => setSidebarExpanded((v) => !v)}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500/40"
            aria-expanded={sidebarExpanded}
            aria-controls="sidebar-main-nav"
            title={sidebarExpanded ? 'Contraer menú' : 'Expandir menú'}
          >
            <HiMenu className="h-6 w-6" aria-hidden />
          </button>
          {sidebarExpanded ? (
            <div className="flex min-w-0 flex-1 items-center gap-2">
              {showHeaderLogo ? (
                <img
                  src={brand.logo_url}
                  alt=""
                  className="h-8 w-auto max-w-[140px] object-contain shrink-0"
                  onError={() => setBrandLogoFailed(true)}
                />
              ) : (
                <div
                  className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-xs font-bold text-white"
                  style={{ backgroundColor: brand.primary_color }}
                >
                  {brandingInitials(brand.app_name)}
                </div>
              )}
              <span className="truncate text-sm font-semibold text-slate-900 dark:text-white">{brand.app_name}</span>
            </div>
          ) : showHeaderLogo ? (
            <img
              src={brand.logo_url}
              alt=""
              className="flex h-8 w-auto max-w-[2.5rem] object-contain shrink-0 rounded"
              title={brand.app_name}
              onError={() => setBrandLogoFailed(true)}
            />
          ) : (
            <div
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-xs font-bold text-white"
              style={{ backgroundColor: brand.primary_color }}
              title={brand.app_name}
            >
              {brandingInitials(brand.app_name)}
            </div>
          )}
        </div>
        <nav id="sidebar-main-nav" className="flex-1 overflow-y-auto overflow-x-hidden py-3 px-2">
          <ul className="space-y-1">
            {visibleNav.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  title={item.label}
                  style={({ isActive }) =>
                    isActive
                      ? {
                          backgroundColor: `${brand.primary_color}22`,
                          color: brand.primary_color,
                        }
                      : undefined
                  }
                  className={({ isActive }) =>
                    clsx(
                      'flex items-center rounded-lg text-sm font-medium transition-colors',
                      sidebarExpanded ? 'gap-3 px-3 py-2.5' : 'justify-center px-0 py-2.5',
                      !isActive &&
                        'text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800',
                    )
                  }
                >
                  {item.icon}
                  <span
                    className={clsx(
                      'truncate transition-opacity duration-200',
                      sidebarExpanded ? 'opacity-100 w-auto' : 'sr-only',
                    )}
                  >
                    {item.label}
                  </span>
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-4 dark:border-slate-800 dark:bg-slate-900 md:px-6">
          <Link
            to="/dashboard"
            className="truncate text-sm font-medium text-slate-700 dark:text-slate-200 md:text-base"
          >
            {brand.app_name}
          </Link>
          <Dropdown
            arrowIcon={false}
            inline
            label={
              <div className="flex items-center gap-2">
                <Avatar rounded size="sm" />
                <div className="hidden text-left md:block">
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
        <main className="flex-1 p-4 md:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
