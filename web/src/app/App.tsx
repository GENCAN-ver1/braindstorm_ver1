import { useEffect } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { SessionProvider, useSession } from '../state/SessionContext'
import { IdeaIntakePage } from '../features/intake/IdeaIntakePage'
import { FrameWizardPage } from '../features/frame/FrameWizardPage'
import { AppShell } from './AppShell'

function RouteSync() {
  const location = useLocation()
  const { setRoute } = useSession()
  useEffect(() => {
    if (location.pathname !== '/') {
      setRoute(location.pathname)
    }
  }, [location.pathname, setRoute])
  return null
}

function RootRedirect() {
  const { state } = useSession()
  const target = state.route && state.route !== '/' ? state.route : '/intake'
  return <Navigate to={target} replace />
}

export function App() {
  return (
    <SessionProvider>
      <RouteSync />
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<RootRedirect />} />
          <Route path="/intake" element={<IdeaIntakePage />} />
          <Route path="/frames/:frameSlug" element={<FrameWizardPage />} />
          <Route path="*" element={<Navigate to="/intake" replace />} />
        </Route>
      </Routes>
    </SessionProvider>
  )
}
