import { useEffect, useState } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import type {
  CreateBrainstormRequest,
  FrameValidationError,
  FrameValue,
  KnowledgeStatus,
} from '../../types/contracts'
import { IDEA_STAGE_TO_MODE, validateFrameContinuation } from '../../types/mappings'
import { getBrainstormApi } from '../../api/client'
import { isBrainstormApiError } from '../../api/errors'
import { useSession } from '../../state/SessionContext'
import { FormError } from '../../components/FormError'
import { StatusBadge, type BadgeTone } from '../../components/StatusBadge'
import {
  FRAME_BY_SLUG,
  FRAME_DEFINITIONS,
  frameIndexBySlug,
  type FrameFieldDefinition,
} from './frameDefinitions'

type AnyFrameValue = FrameValue<string> | FrameValue<string[]>

const KNOWLEDGE_TONE: Record<KnowledgeStatus, BadgeTone> = {
  UNKNOWN: 'danger',
  ASSUMPTION: 'warning',
  KNOWN: 'success',
  CONFLICT: 'warning',
}

function FrameFieldEditor({
  field,
  frameValue,
  error,
  onChange,
}: {
  field: FrameFieldDefinition
  frameValue: AnyFrameValue
  error?: FrameValidationError
  onChange: (value: string | string[]) => void
}) {
  const errorId = `${field.key}-error`

  if (field.kind === 'list') {
    const items = frameValue.value as string[]
    const updateItem = (index: number, value: string) => {
      const next = [...items]
      next[index] = value
      onChange(next)
    }
    const addItem = () => onChange([...items, ''])
    const removeItem = (index: number) => onChange(items.filter((_, i) => i !== index))

    return (
      <div className="frame-field">
        <span id={`${field.key}-label`}>{field.label}</span>
        <StatusBadge tone={KNOWLEDGE_TONE[frameValue.status]}>{frameValue.status}</StatusBadge>
        <div role="group" aria-labelledby={`${field.key}-label`}>
          {items.map((item, index) => (
            <div key={index} className="frame-field__list-item">
              <input
                id={`${field.key}-${index}`}
                name={`${field.key}-${index}`}
                type="text"
                autoComplete="off"
                value={item}
                placeholder={field.placeholder}
                aria-label={`${field.label} item ${index + 1}`}
                aria-describedby={error ? errorId : undefined}
                onChange={(event) => updateItem(index, event.target.value)}
              />
              <button
                type="button"
                onClick={() => removeItem(index)}
                aria-label={`Remove ${field.label} item ${index + 1}`}
              >
                Remove
              </button>
            </div>
          ))}
        </div>
        <button id={`${field.key}-add`} type="button" onClick={addItem}>
          Add {field.label.toLowerCase()}
        </button>
        {error && <FormError id={errorId}>{error.message}</FormError>}
      </div>
    )
  }

  const value = frameValue.value as string
  return (
    <div className="frame-field">
      <label htmlFor={field.key}>{field.label}</label>
      <StatusBadge tone={KNOWLEDGE_TONE[frameValue.status]}>{frameValue.status}</StatusBadge>
      <textarea
        id={field.key}
        name={field.key}
        autoComplete="off"
        value={value}
        placeholder={field.placeholder}
        aria-describedby={error ? errorId : undefined}
        onChange={(event) => onChange(event.target.value)}
      />
      {error && <FormError id={errorId}>{error.message}</FormError>}
    </div>
  )
}

export function FrameWizardPage() {
  const navigate = useNavigate()
  const { frameSlug } = useParams<{ frameSlug: string }>()
  const { state, setFrameValue, setCurrentFrame, setSession } = useSession()
  const [touched, setTouched] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  const frame = frameSlug ? FRAME_BY_SLUG[frameSlug] : undefined
  const index = frameIndexBySlug(frameSlug ?? '')

  useEffect(() => {
    setTouched(false)
    setSubmitError(null)
  }, [frameSlug])

  useEffect(() => {
    setCurrentFrame(index >= 0 ? index : 0)
  }, [index, setCurrentFrame])

  if (!frame) {
    return <Navigate to="/intake" replace />
  }

  const errors = touched ? validateFrameContinuation(state.frames, frame.name) : []
  const errorByField = new Map(errors.map((error) => [error.field, error]))

  const handleContinue = () => {
    setTouched(true)
    const currentErrors = validateFrameContinuation(state.frames, frame.name)
    if (currentErrors.length > 0) {
      const firstField = currentErrors[0].field
      const focusTarget =
        document.getElementById(firstField) ??
        document.getElementById(`${firstField}-0`) ??
        document.getElementById(`${firstField}-add`)
      focusTarget?.focus()
      return
    }
    if (index < FRAME_DEFINITIONS.length - 1) {
      navigate(FRAME_DEFINITIONS[index + 1].route)
    }
  }

  const handleComplete = async () => {
    setTouched(true)
    const currentErrors = validateFrameContinuation(state.frames, frame.name)
    if (currentErrors.length > 0) {
      const firstField = currentErrors[0].field
      const focusTarget =
        document.getElementById(firstField) ??
        document.getElementById(`${firstField}-0`) ??
        document.getElementById(`${firstField}-add`)
      focusTarget?.focus()
      return
    }
    if (!state.selectedIdeaStage) return

    const mode = IDEA_STAGE_TO_MODE[state.selectedIdeaStage]
    const request: CreateBrainstormRequest = { idea: state.idea, mode, frames: state.frames }
    setSubmitting(true)
    setSubmitError(null)
    try {
      const session = await getBrainstormApi().createSession(request)
      setSession(session.id, session.revision)
      navigate('/run')
    } catch (err) {
      setSubmitError(isBrainstormApiError(err) ? err.message : 'Could not start the run.')
      setSubmitting(false)
    }
  }

  const handleBack = () => {
    if (index === 0) {
      navigate('/intake')
    } else {
      navigate(FRAME_DEFINITIONS[index - 1].route)
    }
  }

  const isLastFrame = index === FRAME_DEFINITIONS.length - 1

  return (
    <section aria-labelledby="frame-heading">
      <h1 id="frame-heading">{frame.name}</h1>
      <p>
        Step {index + 1} of {FRAME_DEFINITIONS.length}
      </p>

      {frame.fields.map((field) => (
        <FrameFieldEditor
          key={field.key}
          field={field}
          frameValue={state.frames[field.key]}
          error={errorByField.get(field.key)}
          onChange={(value) => setFrameValue(field.key, value)}
        />
      ))}

      <button type="button" onClick={handleBack} disabled={submitting}>
        Back
      </button>
      <button
        type="button"
        onClick={isLastFrame ? () => void handleComplete() : handleContinue}
        disabled={submitting}
      >
        {isLastFrame ? (submitting ? 'Starting…' : 'Complete') : 'Continue'}
      </button>

      {submitError && <FormError id="wizard-submit-error">{submitError}</FormError>}
    </section>
  )
}
