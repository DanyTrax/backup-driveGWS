import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Profile } from '../api/types'

interface AuthState {
  accessToken: string | null
  refreshToken: string | null
  expiresAt: number | null
  profile: Profile | null
  setTokens: (access: string, refresh: string, expiresIn: number) => void
  setProfile: (profile: Profile | null) => void
  logout: () => void
  isAuthenticated: () => boolean
  hasPermission: (code: string) => boolean
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      accessToken: null,
      refreshToken: null,
      expiresAt: null,
      profile: null,
      setTokens: (access, refresh, expiresIn) =>
        set({ accessToken: access, refreshToken: refresh, expiresAt: Date.now() + expiresIn * 1000 }),
      setProfile: (profile) => set({ profile }),
      logout: () =>
        set({ accessToken: null, refreshToken: null, expiresAt: null, profile: null }),
      isAuthenticated: () => !!get().accessToken,
      hasPermission: (code: string) => !!get().profile?.permissions?.includes(code),
    }),
    { name: 'msa-auth' },
  ),
)
