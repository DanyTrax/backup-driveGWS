import { Routes, Route, Navigate } from 'react-router-dom'
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

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/accounts" element={<AccountsPage />} />
        <Route path="/tasks" element={<TasksPage />} />
        <Route path="/logs" element={<LogsPage />} />
        <Route path="/restore" element={<RestorePage />} />
        <Route path="/webmail" element={<WebmailPage />} />
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
