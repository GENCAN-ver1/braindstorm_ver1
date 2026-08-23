import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { BrainstormSession } from '../../api/BrainstormApi'
import { getBrainstormApi } from '../../api/client'
import { isBrainstormApiError } from '../../api/errors'
import { useSession } from '../../state/SessionContext'
import { StatusBadge } from '../../components/StatusBadge'
import { NeedsInputPanel } from './NeedsInputPanel'
import {
  GOVERNOR_STATUS_LABELS,
  GOVERNOR_STATUS_TONE,
  STAGE_STATUS_LABELS,
} from './stages'

export function RunPage() {
  const navigate = useNavigate()
  const { state, setSession } = useSession()
  const [session, setSessionState] = useState<BrainstormSession | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    const run = async () => {
      if (!state.sessionId) {
        navigate('/intake', { replace: true })
        return
      }
      try {
        const result = await getBrainstormApi().startRun(state.sessionId, state.revision ?? 0)
        if (!cancelled) {
          setSessionState(result)
          setSession(result.id, result.revision)
        }
      } catch (err) {
        if (!cancelled) setError(isBrainstormApiError(err) ? err.message : 'Run failed.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void run()
    return () => {
      cancelled = true
    }
  }, [state.sessionId, state.revision, navigate, setSession])

  if (loading) return <p>Running…</p>
  if (error) return <p role="alert">{error}</p>
  if (!session) return null

  const status = session.governorStatus

  return (
    <section aria-labelledby="run-heading">
      <h1 id="run-heading">Run</h1>
      <p>
        Status:{' '}
        <StatusBadge tone={GOVERNOR_STATUS_TONE[status]}>
          {GOVERNOR_STATUS_LABELS[status]}
        </StatusBadge>
      </p>

      <ol>
        {session.stages.map((stage) => (
          <li key={stage.id}>
            {stage.label}: {STAGE_STATUS_LABELS[stage.status]}
          </li>
        ))}
      </ol>

      {status === 'NEEDS_INPUT' && (
        <NeedsInputPanel
          session={session}
          onResumed={(next) => {
            setSessionState(next)
            setSession(next.id, next.revision)
          }}
        />
      )}
      {status === 'EXPLORE' && (
        <button type="button" onClick={() => navigate('/capabilities')}>
          Configure external capabilities
        </button>
      )}
      {status === 'ITERATE' && (
        <button type="button" onClick={() => navigate('/human-gate')}>
          Go to human gate
        </button>
      )}
      {status === 'COMMIT' && (
        <button type="button" onClick={() => navigate('/handoff')}>
          View final handoff
        </button>
      )}
      {status === 'RESEARCH_REQUIRED' && <p>Research is required (simulation).</p>}
      {status === 'PARK' && <p>The run is parked (simulation).</p>}
    </section>
  )
}
