import { Outlet } from 'react-router-dom'
import { StatusBadge } from '../components/StatusBadge'
import { isDevelopmentMockEnabled } from '../api/client'

export function AppShell() {
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>
      <header className="app-shell__header">
        <span className="app-shell__title">Brainstorm</span>
        {isDevelopmentMockEnabled() ? (
          <StatusBadge tone="warning">Development simulation</StatusBadge>
        ) : (
          <StatusBadge tone="success">DeepSeek v4 Pro · governed</StatusBadge>
        )}
      </header>
      <main id="main-content" className="app-shell__main" tabIndex={-1}>
        <Outlet />
      </main>
    </div>
  )
}
