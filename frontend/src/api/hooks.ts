import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from './client'
import type {
  AccountAccessCheck,
  BackupLog,
  BackupTask,
  GitRefreshResult,
  MailboxFolder,
  MailboxMessageBody,
  MailboxMessagesPage,
  PlatformBackupResult,
  Profile,
  RestoreJob,
  RunTaskResult,
  SetupState,
  WorkspaceAccount,
} from './types'
import { MAILBOX_MESSAGE_TIMEOUT_MS } from './types'

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

export function useMailboxDelegations(userId: string | null) {
  return useQuery({
    queryKey: ['user-mailbox-delegations', userId],
    enabled: !!userId,
    queryFn: async () =>
      (await api.get<string[]>(`/users/${userId as string}/mailbox-delegations`)).data,
  })
}

export function usePutMailboxDelegations() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: { userId: string; accountIds: string[] }) =>
      (
        await api.put<string[]>(`/users/${payload.userId}/mailbox-delegations`, {
          account_ids: payload.accountIds,
        })
      ).data,
    onSuccess: (_data, payload) => {
      void qc.invalidateQueries({ queryKey: ['user-mailbox-delegations', payload.userId] })
      void qc.invalidateQueries({ queryKey: ['profile'] })
      void qc.invalidateQueries({ queryKey: ['accounts'] })
    },
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

/** GYB estimate puede tardar varios minutos; el cliente por defecto corta a 30s. */
const VERIFY_ACCESS_TIMEOUT_MS = 360_000

/** Comprobación síncrona (sin barra de progreso); preferí verify-access/stream + WebSocket en la UI. */
export function useVerifyAccountAccess() {
  return useMutation({
    mutationFn: async (id: string) =>
      (
        await api.get<AccountAccessCheck>(`/accounts/${id}/verify-access`, {
          timeout: VERIFY_ACCESS_TIMEOUT_MS,
        })
      ).data,
  })
}

export function useStartVerifyAccessStream() {
  return useMutation({
    mutationFn: async (accountId: string) =>
      (await api.post<{ session_id: string }>(`/accounts/${accountId}/verify-access/stream`)).data,
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

export function useMailboxFolders(accountId: string | null) {
  return useQuery({
    queryKey: ['mailbox-folders', accountId],
    queryFn: async () => (await api.get<MailboxFolder[]>(`/accounts/${accountId}/mailbox/folders`)).data,
    enabled: Boolean(accountId),
  })
}

export function useMailboxMessages(accountId: string | null, folderId: string, offset: number) {
  return useQuery({
    queryKey: ['mailbox-messages', accountId, folderId, offset],
    queryFn: async () => {
      const params = { folder: folderId, limit: 80, offset }
      return (await api.get<MailboxMessagesPage>(`/accounts/${accountId}/mailbox/messages`, { params }))
        .data
    },
    enabled: Boolean(accountId),
  })
}

export function useMailboxMessage(accountId: string | null, folderId: string, messageKey: string | null) {
  return useQuery({
    queryKey: ['mailbox-message', accountId, folderId, messageKey],
    queryFn: async () => {
      const params = { folder: folderId, key: messageKey! }
      return (
        await api.get<MailboxMessageBody>(`/accounts/${accountId}/mailbox/message`, {
          params,
          timeout: MAILBOX_MESSAGE_TIMEOUT_MS,
        })
      ).data
    },
    enabled: Boolean(accountId && messageKey),
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
    refetchInterval: (q) => (q.state.data?.status === 'running' ? 3000 : false),
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
