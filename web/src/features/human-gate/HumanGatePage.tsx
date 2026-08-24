import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type {
  BrainstormReview,
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
  const [review, setReview] = useState<BrainstormReview | null>(null)

  useEffect(() => {
    if (!state.sessionId) return
    void getBrainstormApi()
      .getSession(state.sessionId)
      .then((session) => setReview(session.review ?? null))
      .catch((err: unknown) =>
        setError(isBrainstormApiError(err) ? err.message : 'Could not load the review.'),
      )
  }, [state.sessionId])

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
      setReview(session.review ?? null)
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

      {review && (
        <section aria-labelledby="model-review-heading" className="model-review">
          <h2 id="model-review-heading">DeepSeek governed review</h2>
          <p>
            Model: {review.model}. Recommendation: <strong>{review.recommendation}</strong>
            {review.confidence === null ? '' : ` (${Math.round(review.confidence * 100)}% confidence)`}
          </p>
          <div className="candidate-grid">
            {review.candidates.map((candidate) => (
              <article key={candidate.id}>
                <h3>{candidate.title}</h3>
                <p>{candidate.oneLiner}</p>
                <p><strong>Mechanism:</strong> {candidate.coreMechanism}</p>
                <p><strong>Value:</strong> {candidate.valueCreated}</p>
                <p><strong>Lens:</strong> {candidate.lens} · {candidate.complexity}</p>
              </article>
            ))}
          </div>
          {review.risks.length > 0 && (
            <>
              <h3>Risks</h3>
              <ul>{review.risks.map((risk) => <li key={risk}>{risk}</li>)}</ul>
            </>
          )}
          {review.cheapestTest && <p><strong>Cheapest test:</strong> {review.cheapestTest}</p>}
          {review.corrections.length > 0 && (
            <>
              <h3>Evaluator corrections</h3>
              <ul>
                {review.corrections.map((correction, index) => (
                  <li key={String(correction.id ?? index)}>
                    {String(correction.issue ?? 'Correction required')}: {' '}
                    {String(correction.required_change ?? 'Review the governed output.')}
                  </li>
                ))}
              </ul>
            </>
          )}
          <p className="usage-receipt">
            Provider receipt: {review.usage.request_id ?? 'unavailable'} · prompt{' '}
            {review.usage.prompt_tokens ?? 'unavailable'} · completion{' '}
            {review.usage.completion_tokens ?? 'unavailable'} tokens
          </p>
        </section>
      )}

      <button type="button" onClick={() => void submit({ kind: 'confirm' })} disabled={submitting}>
        Confirm
      </button>

      <div>
        <label htmlFor="iteration-feedback">Iteration feedback</label>
        <textarea
          id="iteration-feedback"
          name="iteration-feedback"
          autoComplete="off"
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
          name="missing-field"
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
          name="missing-value"
          autoComplete="off"
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
