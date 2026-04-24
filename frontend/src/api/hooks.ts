import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from './client'
import type {
  BackupLog,
  BackupTask,
  GitRefreshResult,
  PlatformBackupResult,
  Profile,
  RestoreJob,
  RunTaskResult,
  SetupState,
  WorkspaceAccount,
} from './types'

export type TaskPayload = {
  name: string
  description?: string | null
  is_enabled: boolean
  scope: string
  mode: string
  schedule_kind: string
  cron_expression?: string | null
  run_at_hour?: number | null
  run_at_minute?: number | null
  timezone: string
  retention_policy: Record<string, unknown>
  filters: Record<string, unknown>
  notify_channels: Record<string, unknown>
  dry_run: boolean
  checksum_enabled: boolean
  max_parallel_accounts: number
  account_ids: string[]
}

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
    mutationFn: async (id: string) => (await api.post<RunTaskResult>(`/tasks/${id}/run`)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
      qc.invalidateQueries({ queryKey: ['backup-logs'] })
    },
  })
}

export function useCancelBackupLog() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (logId: string) => api.post(`/backup/logs/${logId}/cancel`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['backup-logs'] }),
  })
}

export function useCancelBackupBatch() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (batchId: string) =>
      (await api.post<{ revoked_celery: number; cancelled_logs: number }>(`/backup/batches/${batchId}/cancel`))
        .data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['backup-logs'] }),
  })
}

export function useCreateTask() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: TaskPayload) => (await api.post<BackupTask>('/tasks', payload)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tasks'] }),
  })
}

export function useUpdateTask() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, payload }: { id: string; payload: TaskPayload }) =>
      (await api.patch<BackupTask>(`/tasks/${id}`, payload)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tasks'] }),
  })
}

export function useDeleteTask() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/tasks/${id}`)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
      qc.invalidateQueries({ queryKey: ['backup-logs'] })
    },
  })
}

export function useProvisionMailbox() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (accountId: string) => api.post(`/accounts/${accountId}/provision-mailbox`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['accounts'] }),
  })
}

export function useClearMailbox() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (accountId: string) => api.post(`/accounts/${accountId}/mailbox/clear`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['accounts'] }),
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

export function useBackupLogDetail(logId: string | null) {
  return useQuery({
    queryKey: ['backup-log-detail', logId],
    queryFn: async () => (await api.get<BackupLog>(`/backup/logs/${logId}`)).data,
    enabled: Boolean(logId),
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

export function useGitRefresh() {
  return useMutation({
    mutationFn: async () => (await api.post<GitRefreshResult>('/admin/git-refresh')).data,
  })
}

export function usePlatformBackupRun() {
  return useMutation({
    mutationFn: async () => (await api.post<PlatformBackupResult>('/admin/platform-backup')).data,
  })
}
