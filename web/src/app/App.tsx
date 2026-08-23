import { useEffect } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { SessionProvider, useSession } from '../state/SessionContext'
import { IdeaIntakePage } from '../features/intake/IdeaIntakePage'
import { FrameWizardPage } from '../features/frame/FrameWizardPage'
import { RunPage } from '../features/run/RunPage'
import { ExternalCapabilityGate } from '../features/external-capability/ExternalCapabilityGate'
import { HumanGatePage } from '../features/human-gate/HumanGatePage'
import { HandoffPage } from '../features/handoff/HandoffPage'
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
          <Route path="/run" element={<RunPage />} />
          <Route path="/capabilities" element={<ExternalCapabilityGate />} />
          <Route path="/human-gate" element={<HumanGatePage />} />
          <Route path="/handoff" element={<HandoffPage />} />
          <Route path="*" element={<Navigate to="/intake" replace />} />
        </Route>
      </Routes>
    </SessionProvider>
  )
}
