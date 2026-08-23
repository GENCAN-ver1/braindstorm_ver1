import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type {
  FrameSchema,
  HumanGateDecision,
  MissingInputSubmission,
} from '../../api/BrainstormApi'
import { getBrainstormApi } from '../../api/client'
import { isBrainstormApiError } from '../../api/errors'
import { useSession } from '../../state/SessionContext'
import { FRAME_FIELD_KINDS, FRAME_FIELD_LABELS } from '../frame/frameDefinitions'

const FIELD_OPTIONS = Object.keys(FRAME_FIELD_LABELS) as (keyof FrameSchema)[]

export function HumanGatePage() {
  const navigate = useNavigate()
  const { state, setSession } = useSession()
  const [feedback, setFeedback] = useState('')
  const [missingField, setMissingField] = useState<keyof FrameSchema>(FIELD_OPTIONS[0])
  const [missingValue, setMissingValue] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const submit = async (decision: HumanGateDecision) => {
    if (!state.sessionId) {
      navigate('/intake', { replace: true })
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      const session = await getBrainstormApi().submitHumanGate(
        state.sessionId,
        state.revision ?? 0,
        decision,
      )
      setSession(session.id, session.revision)
      if (session.governorStatus === 'COMMIT') navigate('/handoff')
      else if (session.governorStatus === 'NEEDS_INPUT') navigate('/run')
    } catch (err) {
      setError(isBrainstormApiError(err) ? err.message : 'Decision failed.')
    } finally {
      setSubmitting(false)
    }
  }

  const submitMissingInput = () => {
    const isList = FRAME_FIELD_KINDS[missingField] === 'list'
    const value = isList
      ? missingValue
          .split('\n')
          .map((item) => item.trim())
          .filter((item) => item.length > 0)
      : missingValue
    const input = { field: missingField, value, status: 'KNOWN' } as MissingInputSubmission
    void submit({ kind: 'provide_missing_input', input })
  }

  return (
    <section aria-labelledby="human-gate-heading">
      <h1 id="human-gate-heading">Human gate</h1>
      <p>Review the run before committing.</p>

      <button type="button" onClick={() => void submit({ kind: 'confirm' })} disabled={submitting}>
        Confirm
      </button>

      <div>
        <label htmlFor="iteration-feedback">Iteration feedback</label>
        <textarea
          id="iteration-feedback"
          value={feedback}
          onChange={(event) => setFeedback(event.target.value)}
        />
        <button
          type="button"
          onClick={() => void submit({ kind: 'request_iteration', feedback })}
          disabled={submitting}
        >
          Request iteration
        </button>
      </div>

      <div>
        <label htmlFor="missing-field">Field to provide</label>
        <select
          id="missing-field"
          value={missingField}
          onChange={(event) => setMissingField(event.target.value as keyof FrameSchema)}
        >
          {FIELD_OPTIONS.map((field) => (
            <option key={field} value={field}>
              {FRAME_FIELD_LABELS[field]}
            </option>
          ))}
        </select>
        <label htmlFor="missing-value">Value</label>
        <textarea
          id="missing-value"
          value={missingValue}
          onChange={(event) => setMissingValue(event.target.value)}
        />
        <button type="button" onClick={submitMissingInput} disabled={submitting}>
          Provide missing input
        </button>
      </div>

      {error && <p role="alert">{error}</p>}
    </section>
  )
}
