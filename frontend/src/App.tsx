import { Routes, Route, Navigate, useParams } from 'react-router-dom'
import ProtectedRoute from './layouts/ProtectedRoute'
import AppLayout from './layouts/AppLayout'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import AccountsPage from './pages/AccountsPage'
import TasksPage from './pages/TasksPage'
import LogsPage from './pages/LogsPage'
import RestorePage from './pages/RestorePage'
import WizardPage from './pages/WizardPage'
import UsersPage from './pages/UsersPage'
import SettingsPage from './pages/SettingsPage'
import ProfilePage from './pages/ProfilePage'
import WebmailPage from './pages/WebmailPage'
import WebmailAssignPasswordPage from './pages/WebmailAssignPasswordPage'
import MailboxBrowserPage from './pages/MailboxBrowserPage'
import GybWorkBrowserPage from './pages/GybWorkBrowserPage'
import AccountMailDataPage from './pages/AccountMailDataPage'

import { hideMaildirWebmailUi } from './config/ui'

function MailboxRoute() {
  const { accountId } = useParams<{ accountId: string }>()
  if (hideMaildirWebmailUi()) {
    return <Navigate to={`/gyb-work/${accountId ?? ''}`} replace />
  }
  return <MailboxBrowserPage />
}

function WebmailRoute() {
  if (hideMaildirWebmailUi()) {
    return <Navigate to="/dashboard" replace />
  }
  return <WebmailPage />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/webmail/assign-password" element={<WebmailAssignPasswordPage />} />
      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/accounts" element={<AccountsPage />} />
        <Route path="/accounts/:accountId/mailbox" element={<MailboxRoute />} />
        <Route path="/gyb-work" element={<GybWorkBrowserPage />} />
        <Route path="/gyb-work/:accountId" element={<GybWorkBrowserPage />} />
        <Route path="/accounts/:accountId/mail-data" element={<AccountMailDataPage />} />
        <Route path="/tasks" element={<TasksPage />} />
        <Route path="/logs" element={<LogsPage />} />
        <Route path="/restore" element={<RestorePage />} />
        <Route path="/webmail" element={<WebmailRoute />} />
        <Route path="/setup" element={<WizardPage />} />
        <Route path="/users" element={<UsersPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/profile" element={<ProfilePage />} />
      </Route>
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}
