import { useState } from 'react'
import type { BrainstormSession, MissingInputSubmission } from '../../api/BrainstormApi'
import { findMissingFrameFields } from '../../api/developmentMock'
import { getBrainstormApi } from '../../api/client'
import { isBrainstormApiError } from '../../api/errors'
import { FormError } from '../../components/FormError'
import { FRAME_FIELD_LABELS, LIST_FIELD_KEYS } from '../frame/frameDefinitions'

export function NeedsInputPanel({
  session,
  onResumed,
}: {
  session: BrainstormSession
  onResumed: (session: BrainstormSession) => void
}) {
  const missing = findMissingFrameFields(session.frames)
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const setDraft = (field: string, value: string) =>
    setDrafts((prev) => ({ ...prev, [field]: value }))

  const handleResume = async () => {
    setSubmitting(true)
    setError(null)
    let current = session
    try {
      const api = getBrainstormApi()
      for (const field of missing) {
        const text = drafts[field] ?? ''
        if (text.trim().length === 0) continue
        const value = LIST_FIELD_KEYS.has(field)
          ? text
              .split('\n')
              .map((item) => item.trim())
              .filter((item) => item.length > 0)
          : text
        const input = { field, value, status: 'KNOWN' } as MissingInputSubmission
        current = await api.resumeRun(current.id, current.revision, input)
      }
      onResumed(current)
    } catch (err) {
      setError(isBrainstormApiError(err) ? err.message : 'Resume failed.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section aria-labelledby="needs-input-heading">
      <h2 id="needs-input-heading">Provide missing information</h2>
      {missing.map((field) => (
        <div key={field} className="frame-field">
          <label htmlFor={`missing-${field}`}>{FRAME_FIELD_LABELS[field]}</label>
          <textarea
            id={`missing-${field}`}
            name={`missing-${field}`}
            autoComplete="off"
            value={drafts[field] ?? ''}
            placeholder={LIST_FIELD_KEYS.has(field) ? 'One item per line' : undefined}
            onChange={(event) => setDraft(field, event.target.value)}
          />
        </div>
      ))}
      <button type="button" onClick={handleResume} disabled={submitting}>
        {submitting ? 'Resuming…' : 'Resume'}
      </button>
      {error && <FormError id="needs-input-error">{error}</FormError>}
    </section>
  )
}
