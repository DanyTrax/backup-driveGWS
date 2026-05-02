import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from './client'
import type {
  AccountAccessCheck,
  AccountMailPurgePayload,
  AccountMailPurgeResult,
  BackupLog,
  BackupTask,
  BrandingConfig,
  BrandingPublic,
  GitRefreshResult,
  GybWorkAccount,
  GybWorkMessagesPage,
  HostOpsConfig,
  HostOpsSchedule,
  StackDeployJobStart,
  StackDeployJobStatus,
  StackDeployMode,
  MailboxFolder,
  MailboxMessageBody,
  MailboxMessagesPage,
  MailDataInventory,
  MaildirRebuildFromGybResult,
  PlatformBackupResult,
  Profile,
  PurgeAllLocalMailResult,
  RestoreJob,
  RunTaskResult,
  SetupState,
  WorkspaceAccount,
} from './types'
import {
  MAILBOX_LIST_TIMEOUT_MS,
  MAILBOX_MESSAGE_TIMEOUT_MS,
  MAILDATA_INVENTORY_TIMEOUT_MS,
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
    queryFn: async () => (await api.get<BrandingPublic>('/meta/branding')).data,
    staleTime: 60_000,
  })
}

export function useBrandingConfig() {
  return useQuery({
    queryKey: ['branding-config'],
    queryFn: async () => (await api.get<BrandingConfig>('/settings/branding-config')).data,
  })
}

export type BrandingUpdatePayload = {
  app_name?: string
  primary_color?: string
  accent_color?: string
  logo_url?: string
}

export function useUpdateBranding() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: BrandingUpdatePayload) =>
      (await api.put<BrandingPublic>('/settings/branding', payload)).data,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['branding'] })
      void qc.invalidateQueries({ queryKey: ['branding-config'] })
    },
  })
}

export function useUploadBrandingLogo() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (file: File) => {
      const body = new FormData()
      body.append('file', file)
      return (await api.post<BrandingPublic>('/settings/branding/logo', body)).data
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['branding'] })
      void qc.invalidateQueries({ queryKey: ['branding-config'] })
    },
  })
}

export function useDeleteBrandingLogo() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => (await api.delete<BrandingPublic>('/settings/branding/logo')).data,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['branding'] })
      void qc.invalidateQueries({ queryKey: ['branding-config'] })
    },
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

export function useDeleteBackupLog() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (logId: string) => {
      await api.delete(`/backup/logs/${logId}`)
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['backup-logs'] })
      void qc.invalidateQueries({ queryKey: ['backup-log-detail'] })
    },
  })
}

export interface BackupLogBulkDeleteResult {
  deleted: number
  skipped_running: string[]
  not_found: string[]
}

export function useDeleteBackupLogsBulk() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (logIds: string[]) =>
      (await api.post<BackupLogBulkDeleteResult>('/backup/logs/bulk-delete', { log_ids: logIds })).data,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['backup-logs'] })
      void qc.invalidateQueries({ queryKey: ['backup-log-detail'] })
    },
  })
}

export async function downloadBackupLogsPdf(params: { status?: string; taskId?: string }) {
  const query = new URLSearchParams()
  if (params.status) query.set('status', params.status)
  if (params.taskId) query.set('task_id', params.taskId)
  const res = await api.get(`/backup/logs/export.pdf?${query.toString()}`, {
    responseType: 'blob',
    timeout: 120_000,
  })
  const blob = new Blob([res.data], { type: 'application/pdf' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')
  a.download = `backup-logs-${stamp}.pdf`
  a.click()
  URL.revokeObjectURL(url)
}

export function useRetryGmailVault() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (logId: string) =>
      (await api.post<{ queued: boolean; celery_id: string }>(`/backup/logs/${logId}/retry-gmail-vault`)).data,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['backup-logs'] })
      void qc.invalidateQueries({ queryKey: ['backup-log-detail'] })
    },
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

export function useMailDataInventory(accountId: string | null, enabled = true) {
  return useQuery({
    queryKey: ['mail-data-inventory', accountId],
    queryFn: async () =>
      (
        await api.get<MailDataInventory>(`/accounts/${accountId}/mail-data-inventory`, {
          timeout: MAILDATA_INVENTORY_TIMEOUT_MS,
        })
      ).data,
    enabled: Boolean(accountId) && enabled,
    retry: 1,
  })
}

export function usePurgeAccountMailData() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (args: { accountId: string; payload: AccountMailPurgePayload }) =>
      (
        await api.post<AccountMailPurgeResult>(
          `/accounts/${args.accountId}/mail-data-purge`,
          args.payload,
        )
      ).data,
    onSuccess: (_data, args) => {
      void qc.invalidateQueries({ queryKey: ['accounts'] })
      void qc.invalidateQueries({ queryKey: ['mail-data-inventory', args.accountId] })
    },
  })
}

export function useRebuildMaildirFromLocalGyb() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (accountId: string) =>
      (
        await api.post<MaildirRebuildFromGybResult>(
          `/accounts/${accountId}/maildir/rebuild-from-local-gyb`,
        )
      ).data,
    onSuccess: (_data, accountId) => {
      void qc.invalidateQueries({ queryKey: ['accounts'] })
      void qc.invalidateQueries({ queryKey: ['mail-data-inventory', accountId] })
      void qc.invalidateQueries({ queryKey: ['mailbox-folders', accountId] })
      void qc.invalidateQueries({ queryKey: ['backup-logs'] })
    },
  })
}

export function usePurgeAllLocalMail() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (confirmation: string) =>
      (await api.post<PurgeAllLocalMailResult>('/settings/purge-all-local-mail', { confirmation })).data,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['accounts'] })
    },
  })
}

export function useMailboxFolders(accountId: string | null) {
  return useQuery({
    queryKey: ['mailbox-folders', accountId],
    queryFn: async () => (await api.get<MailboxFolder[]>(`/accounts/${accountId}/mailbox/folders`)).data,
    enabled: Boolean(accountId),
  })
}

export function useMailboxMessages(
  accountId: string | null,
  folderId: string,
  offset: number,
  opts?: { q?: string; sortBy?: 'mtime' | 'header_date'; sortOrder?: 'desc' | 'asc' },
) {
  const q = (opts?.q ?? '').trim()
  const sortBy = opts?.sortBy ?? 'header_date'
  const sortOrder = opts?.sortOrder ?? 'desc'
  return useQuery({
    queryKey: ['mailbox-messages', accountId, folderId, offset, q, sortBy, sortOrder],
    queryFn: async () => {
      const params: Record<string, string | number> = {
        folder: folderId,
        limit: 80,
        offset,
        sort_by: sortBy,
        sort_order: sortOrder,
      }
      if (q) params.q = q
      return (
        await api.get<MailboxMessagesPage>(`/accounts/${accountId}/mailbox/messages`, {
          params,
          timeout: MAILBOX_LIST_TIMEOUT_MS,
        })
      ).data
    },
    enabled: Boolean(accountId),
    retry: 1,
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

export function useGybWorkAccounts() {
  return useQuery({
    queryKey: ['gyb-work-accounts'],
    queryFn: async () => (await api.get<GybWorkAccount[]>('/accounts/gyb-work/accounts')).data,
  })
}

export function useGybWorkFolders(accountId: string | null, view: 'disk' | 'labels') {
  return useQuery({
    queryKey: ['gyb-work-folders', accountId, view],
    queryFn: async () =>
      (await api.get<MailboxFolder[]>(`/accounts/${accountId}/gyb-work/folders`, { params: { view } }))
        .data,
    enabled: Boolean(accountId),
  })
}

export function useGybWorkMessages(
  accountId: string | null,
  params: {
    view: 'disk' | 'labels'
    folderId: string
    labelId: string
    q: string
    offset: number
    listScope: 'folder' | 'all'
    sortBy: 'header_date' | 'mtime'
    sortOrder: 'desc' | 'asc'
  },
) {
  const { view, folderId, labelId, q, offset, listScope, sortBy, sortOrder } = params
  return useQuery({
    queryKey: [
      'gyb-work-messages',
      accountId,
      view,
      folderId,
      labelId,
      q,
      offset,
      listScope,
      sortBy,
      sortOrder,
    ],
    queryFn: async () => {
      const reqParams: Record<string, string | number> = {
        view,
        limit: 80,
        offset,
        list_scope: listScope,
        sort_by: sortBy,
        sort_order: sortOrder,
      }
      if (view === 'disk') reqParams.folder = folderId
      else reqParams.label = labelId
      if (q) reqParams.q = q
      return (
        await api.get<GybWorkMessagesPage>(`/accounts/${accountId}/gyb-work/messages`, {
          params: reqParams,
          timeout: MAILBOX_LIST_TIMEOUT_MS,
        })
      ).data
    },
    enabled:
      Boolean(accountId) &&
      (listScope === 'all' || view === 'disk' || Boolean(labelId)),
  })
}

export function useGybWorkMessage(accountId: string | null, messageKey: string | null) {
  return useQuery({
    queryKey: ['gyb-work-message', accountId, messageKey],
    queryFn: async () =>
      (
        await api.get<MailboxMessageBody>(`/accounts/${accountId}/gyb-work/message`, {
          params: { key: messageKey! },
          timeout: MAILBOX_MESSAGE_TIMEOUT_MS,
        })
      ).data,
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

export function useHostOpsConfig() {
  return useQuery({
    queryKey: ['host-ops-config'],
    queryFn: async () => (await api.get<HostOpsConfig>('/admin/host-ops/config')).data,
  })
}

export function useDockerPruneRun() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (preset: 'light' | 'deep') =>
      (await api.post<Record<string, unknown>>('/admin/host-ops/docker-prune', { preset })).data,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['host-ops-config'] })
    },
  })
}

export function useHostOpsScheduleSave() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: HostOpsSchedule) =>
      (await api.put<HostOpsSchedule>('/admin/host-ops/docker-prune-schedule', payload)).data,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['host-ops-config'] })
    },
  })
}

export function useStackDeployRun() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (mode: StackDeployMode) =>
      (await api.post<StackDeployJobStart>('/admin/host-ops/stack-deploy', { mode })).data,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['host-ops-config'] })
    },
  })
}

export function useStackDeployJob(jobName: string | null) {
  return useQuery({
    queryKey: ['stack-deploy-job', jobName],
    queryFn: async () =>
      (await api.get<StackDeployJobStatus>(`/admin/host-ops/stack-deploy-job/${jobName as string}`)).data,
    enabled: Boolean(jobName),
    refetchInterval: (q) => {
      const d = q.state.data
      if (!d) return 2500
      return d.phase === 'running' ? 2500 : false
    },
  })
}
