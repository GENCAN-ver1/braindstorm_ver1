import { Outlet } from 'react-router-dom'
import { StatusBadge } from '../components/StatusBadge'

export function AppShell() {
  return (
    <div className="app-shell">
      <header className="app-shell__header">
        <span className="app-shell__title">Brainstorm</span>
        <StatusBadge tone="warning">Development simulation</StatusBadge>
      </header>
      <main className="app-shell__main">
        <Outlet />
      </main>
    </div>
  )
}
