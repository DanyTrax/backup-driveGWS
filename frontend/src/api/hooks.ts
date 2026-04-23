import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from './client'
import type {
  BackupLog,
  BackupTask,
  Profile,
  RestoreJob,
  SetupState,
  WorkspaceAccount,
} from './types'

export function useProfile() {
  return useQuery({
    queryKey: ['profile'],
    queryFn: async () => (await api.get<Profile>('/auth/me')).data,
  })
}

export function useBranding() {
  return useQuery({
    queryKey: ['branding'],
    queryFn: async () => (await api.get<Record<string, string>>('/meta/branding')).data,
  })
}

export function useAccounts(enabled?: boolean) {
  return useQuery({
    queryKey: ['accounts', enabled],
    queryFn: async () => {
      const params = enabled === undefined ? {} : { enabled }
      return (await api.get<WorkspaceAccount[]>('/accounts', { params })).data
    },
  })
}

export function useSyncAccounts() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => (await api.post('/accounts/sync')).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['accounts'] }),
  })
}

export function useApproveAccount() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => (await api.post(`/accounts/${id}/approve`, {})).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['accounts'] }),
  })
}

export function useRevokeAccount() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => (await api.post(`/accounts/${id}/revoke`, {})).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['accounts'] }),
  })
}

export function useTasks() {
  return useQuery({
    queryKey: ['tasks'],
    queryFn: async () => (await api.get<BackupTask[]>('/tasks')).data,
  })
}

export function useRunTask() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => (await api.post(`/tasks/${id}/run`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tasks'] }),
  })
}

export function useBackupLogs(params?: { status?: string; taskId?: string }) {
  return useQuery({
    queryKey: ['backup-logs', params],
    queryFn: async () => {
      const query = new URLSearchParams()
      if (params?.status) query.set('status', params.status)
      if (params?.taskId) query.set('task_id', params.taskId)
      return (await api.get<BackupLog[]>(`/backup/logs?${query.toString()}`)).data
    },
    refetchInterval: 5000,
  })
}

export function useRestoreJobs() {
  return useQuery({
    queryKey: ['restore-jobs'],
    queryFn: async () => (await api.get<RestoreJob[]>('/restore')).data,
    refetchInterval: 5000,
  })
}

export function useSetupState() {
  return useQuery({
    queryKey: ['setup-state'],
    queryFn: async () => (await api.get<SetupState>('/setup/state')).data,
  })
}
