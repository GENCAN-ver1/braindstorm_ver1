import { useEffect, useState } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import type {
  FrameValidationError,
  FrameValue,
  KnowledgeStatus,
} from '../../types/contracts'
import { validateFrameContinuation } from '../../types/mappings'
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
                type="text"
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
        <button type="button" onClick={addItem}>
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
        value={value}
        placeholder={field.placeholder}
        aria-describedby={error ? errorId : undefined}
        onChange={(event) => onChange(event.target.value)}
      />
      {error && <FormError id={errorId}>{error.message}</FormError>}
    </div>
  )
}

function FrameSummary() {
  const { state } = useSession()
  return (
    <section aria-labelledby="summary-heading">
      <h1 id="summary-heading">Frame wizard complete</h1>
      <dl>
        {FRAME_DEFINITIONS.flatMap((frame) => frame.fields).map((field) => {
          const frameValue = state.frames[field.key]
          const value = Array.isArray(frameValue.value)
            ? frameValue.value.join(', ')
            : frameValue.value
          return (
            <div key={field.key}>
              <dt>{field.label}</dt>
              <dd>
                {value || '\u2014'}
                <StatusBadge tone={KNOWLEDGE_TONE[frameValue.status]}>
                  {frameValue.status}
                </StatusBadge>
              </dd>
            </div>
          )
        })}
      </dl>
    </section>
  )
}

export function FrameWizardPage() {
  const navigate = useNavigate()
  const { frameSlug } = useParams<{ frameSlug: string }>()
  const { state, setFrameValue, setCurrentFrame } = useSession()
  const [touched, setTouched] = useState(false)
  const [wizardComplete, setWizardComplete] = useState(false)

  const frame = frameSlug ? FRAME_BY_SLUG[frameSlug] : undefined
  const index = frameIndexBySlug(frameSlug ?? '')

  useEffect(() => {
    setTouched(false)
    setWizardComplete(false)
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
    if (currentErrors.length > 0) return
    if (index < FRAME_DEFINITIONS.length - 1) {
      navigate(FRAME_DEFINITIONS[index + 1].route)
    } else {
      setWizardComplete(true)
    }
  }

  const handleBack = () => {
    if (index === 0) {
      navigate('/intake')
    } else {
      navigate(FRAME_DEFINITIONS[index - 1].route)
    }
  }

  if (wizardComplete) {
    return <FrameSummary />
  }

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

      <button type="button" onClick={handleBack}>
        Back
      </button>
      <button type="button" onClick={handleContinue}>
        {index < FRAME_DEFINITIONS.length - 1 ? 'Continue' : 'Complete'}
      </button>
    </section>
  )
}
