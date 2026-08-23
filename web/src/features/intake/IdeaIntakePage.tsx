import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { IdeaStageChoice } from '../../types/contracts'
import { IDEA_STAGE_TO_MODE } from '../../types/mappings'
import { useSession } from '../../state/SessionContext'
import { FormError } from '../../components/FormError'

const STAGE_CHOICES = Object.keys(IDEA_STAGE_TO_MODE) as IdeaStageChoice[]

export function IdeaIntakePage() {
  const navigate = useNavigate()
  const { state, setIdea, selectIdeaStage } = useSession()
  const [touched, setTouched] = useState(false)

  const ideaBlank = state.idea.trim().length === 0
  const stageMissing = state.selectedIdeaStage === undefined
  const ideaError = touched && ideaBlank ? 'Describe your idea before continuing.' : null
  const stageError =
    touched && stageMissing ? 'Choose how you want to proceed before continuing.' : null

  const handleContinue = () => {
    setTouched(true)
    if (ideaBlank || stageMissing) return
    navigate('/frames/who-and-job')
  }

  return (
    <section aria-labelledby="intake-heading">
      <h1 id="intake-heading">Start a brainstorm</h1>

      <fieldset>
        <legend>How do you want to proceed?</legend>
        {STAGE_CHOICES.map((choice) => (
          <label key={choice}>
            <input
              type="radio"
              name="idea-stage"
              value={choice}
              checked={state.selectedIdeaStage === choice}
              onChange={() => selectIdeaStage(choice)}
            />
            {choice}
          </label>
        ))}
        {stageError && <FormError id="idea-stage-error">{stageError}</FormError>}
      </fieldset>

      <div className="form-field">
        <label htmlFor="idea">What is your idea?</label>
        <textarea
          id="idea"
          value={state.idea}
          onChange={(event) => setIdea(event.target.value)}
          aria-describedby={ideaError ? 'idea-error' : undefined}
        />
        {ideaError && <FormError id="idea-error">{ideaError}</FormError>}
      </div>

      <button type="button" onClick={handleContinue}>
        Continue
      </button>
    </section>
  )
}
