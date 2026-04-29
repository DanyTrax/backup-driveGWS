export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
  mfa_required?: boolean
  mfa_challenge?: string | null
}

export interface Profile {
  id: string
  email: string
  full_name: string
  role_code: string
  mfa_enabled: boolean
  must_change_password: boolean
  status: string
  preferred_locale: string
  preferred_timezone: string
  last_login_at: string | null
  permissions: string[]
  /** Solo aplica con permiso mailbox.view_delegated (sin view_all). */
  mailbox_delegated_account_ids?: string[]
}

export const MAILBOX_MESSAGE_TIMEOUT_MS = 120_000

export interface MailboxFolder {
  id: string
  name: string
}

export interface MailboxMessageSummary {
  id: string
  subject: string
  from: string
  date: string | null
  size: number
}

export interface MailboxMessagesPage {
  folder_id: string
  offset: number
  limit: number
  total_estimated: number | null
  items: MailboxMessageSummary[]
}

export interface MailboxMessageBody {
  id: string
  subject: string
  from: string
  date: string | null
  text_plain: string | null
  text_html: string | null
}

export interface AccountAccessCheck {
  account_id: string
  email: string
  drive_ok: boolean
  drive_detail: string | null
  gmail_ok: boolean
  gmail_detail: string | null
  maildir_path: string | null
  maildir_layout_ok: boolean
}

export interface WorkspaceAccount {
  id: string
  email: string
  full_name: string | null
  org_unit_path: string | null
  is_workspace_admin: boolean
  workspace_status: string
  is_backup_enabled: boolean
  backup_enabled_at: string | null
  imap_enabled: boolean
  drive_vault_folder_id: string | null
  last_sync_at: string | null
  last_successful_backup_at: string | null
  total_bytes_cache: number | null
  total_messages_cache: number | null
  maildir_on_disk: boolean
  maildir_user_cleared_at: string | null
}

/** Debe coincidir con ``PURGE_ALL_MAIL_LOCAL_CONFIRM_PHRASE`` en el backend. */
export const PURGE_ALL_LOCAL_MAIL_CONFIRM_PHRASE =
  'ELIMINAR_TODAS_LAS_COPIAS_LOCALES_DE_CORREO'

export interface MailDataInventory {
  account_id: string
  email: string
  maildir_root: string
  maildir_on_disk: boolean
  maildir_size_bytes: number | null
  gyb_work_path: string
  gyb_work_has_content: boolean
  gyb_work_size_bytes: number | null
  gmail_backup_logs_count: number
  webmail_tokens_count: number
  imap_enabled: boolean
  imap_password_configured: boolean
}

export interface AccountMailPurgePayload {
  confirmation_email: string
  maildir: boolean
  gyb_workdir: boolean
  gmail_backup_logs: boolean
  webmail_tokens: boolean
  revoke_imap_credentials: boolean
}

export interface AccountMailPurgeResult {
  maildir_cleared: number
  gyb_workdir_cleared: number
  gmail_logs_deleted: number
  webmail_tokens_deleted: number
  imap_credentials_revoked: boolean
}

export interface PurgeAllLocalMailResult {
  workspace_accounts: number
  maildirs_cleared: number
  gyb_workdirs_cleared: number
  gmail_backup_logs_deleted: number
  webmail_tokens_deleted: number
}

export interface BackupTask {
  id: string
  name: string
  description: string | null
  is_enabled: boolean
  scope: string
  mode: string
  schedule_kind: string
  cron_expression: string | null
  run_at_hour: number | null
  run_at_minute: number | null
  timezone: string
  retention_policy: Record<string, unknown>
  filters: Record<string, unknown>
  notify_channels: Record<string, unknown>
  dry_run: boolean
  checksum_enabled: boolean
  max_parallel_accounts: number
  account_ids: string[]
  last_run_at: string | null
  last_status: string | null
  created_at: string
}

export interface RunEstimatePart {
  min_minutes: number | null
  max_minutes: number | null
  basis: string
}

export interface RunEstimateItem {
  email: string
  gmail: RunEstimatePart | null
  drive: RunEstimatePart | null
}

export interface RunEstimateOut {
  task_id: string
  scope: string
  mode: string
  items: RunEstimateItem[]
  sum_minutes_min: number | null
  sum_minutes_max: number | null
  disclaimer: string
}

export interface BackupLog {
  id: string
  task_id: string
  account_id: string
  run_batch_id: string | null
  status: string
  scope: string
  mode: string
  started_at: string | null
  finished_at: string | null
  bytes_transferred: number
  files_count: number
  messages_count: number
  errors_count: number
  celery_task_id: string | null
  sha256_manifest_path: string | null
  destination_path: string | null
  error_summary: string | null
  /** Tras importar Maildir: correo local listo (IMAP/visor) antes del vault */
  gmail_maildir_ready_at?: string | null
  /** Subida 1-GMAIL/gyb_mbox completada (o omitida según política de tarea) */
  gmail_vault_completed_at?: string | null
  /** Nombre de la definición de tarea (backup_tasks.name) */
  task_name?: string | null
  /** Correo Workspace de la cuenta ejecutada */
  account_email?: string | null
  /** Último evento de progreso (Redis); útil cuando status === running */
  live_progress?: Record<string, unknown> | null
}

export interface SkippedActiveBackup {
  account_id: string
  email?: string | null
  kind: string
  active_log_id: string
}

export interface RunTaskResult {
  queued: number
  celery_ids: string[]
  batch_id: string
  skipped_due_to_active?: SkippedActiveBackup[]
}

export interface RestoreJob {
  id: string
  target_account_id: string
  scope: string
  status: string
  dry_run: boolean
  items_total: number
  items_restored: number
  items_failed: number
  bytes_restored: number
  started_at: string | null
  finished_at: string | null
  error_summary: string | null
  created_at: string
}

export interface SetupState {
  completed: boolean
  current_step: string
  steps: Record<string, boolean>
  google_client_id: string | null
  required_scopes: string[]
}

export interface GitRefreshStep {
  cmd: string
  rc: number
  stdout: string
  stderr: string
}

export interface GitRefreshResult {
  ok: boolean
  error?: string
  hint?: string
  head?: string
  steps?: GitRefreshStep[]
}

export interface PlatformBackupResult {
  ok: boolean
  error?: string
  reason?: string
  file_id?: string
  filename?: string
  retention_deleted?: string[]
}
