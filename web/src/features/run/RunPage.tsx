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
  const [retryable, setRetryable] = useState(false)
  const [loading, setLoading] = useState(true)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    const run = async () => {
      if (!state.sessionId) {
        navigate('/intake', { replace: true })
        return
      }
      setLoading(true)
      setError(null)
      setRetryable(false)
      try {
        const result = await getBrainstormApi().startRun(state.sessionId, state.revision ?? 0)
        if (!cancelled) {
          setSessionState(result)
          setSession(result.id, result.revision)
        }
      } catch (err) {
        if (!cancelled) {
          setError(isBrainstormApiError(err) ? err.message : 'Run failed.')
          setRetryable(isBrainstormApiError(err) && err.retryable)
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void run()
    return () => {
      cancelled = true
    }
  }, [state.sessionId, state.revision, navigate, setSession, attempt])

  if (loading) return <p role="status" aria-live="polite">Running…</p>
  if (error) {
    return (
      <section aria-labelledby="run-error-heading">
        <h1 id="run-error-heading">Run interrupted</h1>
        <p role="alert">{error}</p>
        {retryable && (
          <button type="button" onClick={() => setAttempt((value) => value + 1)}>
            Retry run
          </button>
        )}
        <button type="button" onClick={() => navigate('/frames/who-and-job')}>
          Start a revised session
        </button>
      </section>
    )
  }
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
      {status === 'RESEARCH_REQUIRED' && <p>Research is required.</p>}
      {status === 'PARK' && <p>The run is parked.</p>}
    </section>
  )
}
