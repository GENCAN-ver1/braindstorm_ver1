import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { CapabilityProvider, CapabilityRequest } from '../../api/BrainstormApi'
import { getBrainstormApi } from '../../api/client'
import { isBrainstormApiError } from '../../api/errors'
import { useSession } from '../../state/SessionContext'
import { CouncilForm } from './CouncilForm'

export function ExternalCapabilityGate() {
  const navigate = useNavigate()
  const { state, setSession } = useSession()
  const [showCouncil, setShowCouncil] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const configure = async (request: CapabilityRequest) => {
    if (!state.sessionId) {
      navigate('/intake', { replace: true })
      return
    }
    setError(null)
    try {
      const session = await getBrainstormApi().configureCapabilities(
        state.sessionId,
        state.revision ?? 0,
        request,
      )
      setSession(session.id, session.revision)
      navigate('/human-gate')
    } catch (err) {
      setError(isBrainstormApiError(err) ? err.message : 'Configuration failed.')
    }
  }

  const handleSkip = () =>
    configure({ capability: 'council', outcome: 'skip', authorized: false })

  const handleEnableCouncil = (providers: CapabilityProvider[]) =>
    configure({
      capability: 'council',
      outcome: 'enable',
      authorized: true,
      providers: providers as [CapabilityProvider, CapabilityProvider, ...CapabilityProvider[]],
    })

  return (
    <section aria-labelledby="capability-heading">
      <h1 id="capability-heading">External capabilities</h1>
      <p>Research, Council, and Evaluator share one authorization gate.</p>
      <button type="button" onClick={handleSkip}>
        Skip capabilities
      </button>
      <button type="button" onClick={() => setShowCouncil(true)}>
        Enable Council
      </button>
      {showCouncil && <CouncilForm onConfigure={handleEnableCouncil} />}
      {error && <p role="alert">{error}</p>}
    </section>
  )
}
