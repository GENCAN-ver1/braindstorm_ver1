import type {
  FrameName,
  FrameSchema,
  FrameValidationError,
  FrameValue,
  GovernorMode,
  IdeaStageChoice,
} from './contracts'

export const IDEA_STAGE_TO_MODE = {
  'I just have an idea': 'Shape',
  'I want to explore possibilities': 'Spark',
  'I already have a solution': 'Stress',
  'I need to make a decision': 'Decide',
} as const satisfies Record<IdeaStageChoice, GovernorMode>

export const FRAME_CANONICAL_FIELDS = {
  'Who & Job': ['target_user', 'core_task'],
  'Desired Change': ['desired_change'],
  Constraints: ['hard_constraints'],
  Success: ['success_metrics'],
  'Failure Boundary': ['abandonment_criteria'],
  'Scope & Validation': ['non_goals', 'validation_horizon'],
} as const satisfies Record<FrameName, readonly (keyof FrameSchema)[]>

const FIELD_LABELS: Record<keyof FrameSchema, string> = {
  target_user: 'Target user',
  core_task: 'Core task',
  desired_change: 'Desired change',
  hard_constraints: 'Hard constraints',
  success_metrics: 'Success metrics',
  abandonment_criteria: 'Abandonment criteria',
  non_goals: 'Non-goals',
  validation_horizon: 'Validation horizon',
}

const isBlank = (value: string | string[]): boolean =>
  typeof value === 'string'
    ? value.trim().length === 0
    : value.length === 0 || value.every((item) => item.trim().length === 0)

export const createAiSuggestion = <T>(value: T): FrameValue<T> => ({
  value,
  status: 'ASSUMPTION',
  source: 'ai',
})

export const validateFrameContinuation = (
  frames: FrameSchema,
  frameName: FrameName,
): FrameValidationError[] =>
  FRAME_CANONICAL_FIELDS[frameName].flatMap((field) => {
    const frameValue = frames[field]
    const label = FIELD_LABELS[field]

    if (frameValue.status === 'UNKNOWN') {
      return [
        {
          field,
          message: `${label} is unknown. Provide a value and classify its evidence before continuing.`,
        },
      ]
    }

    if (isBlank(frameValue.value)) {
      return [{ field, message: `${label} is blank. Provide a value before continuing.` }]
    }

    return []
  })
