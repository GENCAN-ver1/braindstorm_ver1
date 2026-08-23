import type {
  FrameSchema,
  FrameValue,
  FrontendSessionState,
  IdeaStageChoice,
  KnowledgeStatus,
} from '../types/contracts'

export const FRONTEND_SESSION_STORAGE_KEY = 'brainstorm.frontend-session.v1'

const PERSISTENCE_VERSION = 1
const MAX_SESSION_ID_LENGTH = 128
const MAX_IDEA_LENGTH = 4_000
const MAX_FRAME_TEXT_LENGTH = 2_000
const MAX_LIST_LENGTH = 50
const MAX_LIST_ITEM_LENGTH = 500

const ALLOWED_ROUTES = new Set([
  '/',
  '/intake',
  '/frames/who-and-job',
  '/frames/desired-change',
  '/frames/constraints',
  '/frames/success',
  '/frames/failure-boundary',
  '/frames/scope-and-validation',
  '/run',
  '/capabilities',
  '/human-gate',
  '/handoff',
])

export type PersistenceResult =
  | { ok: true }
  | { ok: false; reason: 'storage_unavailable' }

interface PersistedFrontendSession {
  version: typeof PERSISTENCE_VERSION
  state: FrontendSessionState
}

const cloneStringValue = (frame: FrameValue<string>): FrameValue<string> => ({
  value: frame.value,
  status: frame.status,
  source: frame.source,
})

const cloneListValue = (frame: FrameValue<string[]>): FrameValue<string[]> => ({
  value: [...frame.value],
  status: frame.status,
  source: frame.source,
})

const cloneFrames = (frames: FrameSchema): FrameSchema => ({
  target_user: cloneStringValue(frames.target_user),
  core_task: cloneStringValue(frames.core_task),
  desired_change: cloneStringValue(frames.desired_change),
  hard_constraints: cloneListValue(frames.hard_constraints),
  success_metrics: cloneListValue(frames.success_metrics),
  abandonment_criteria: cloneListValue(frames.abandonment_criteria),
  non_goals: cloneListValue(frames.non_goals),
  validation_horizon: cloneStringValue(frames.validation_horizon),
})

const toAllowlistedProjection = (state: FrontendSessionState): FrontendSessionState => ({
  ...(state.sessionId === undefined ? {} : { sessionId: state.sessionId }),
  ...(state.revision === undefined ? {} : { revision: state.revision }),
  route: state.route,
  idea: state.idea,
  ...(state.selectedIdeaStage === undefined
    ? {}
    : { selectedIdeaStage: state.selectedIdeaStage }),
  currentFrame: state.currentFrame,
  frames: cloneFrames(state.frames),
})

export const persistFrontendSessionState = (
  storage: Storage,
  state: FrontendSessionState,
): PersistenceResult => {
  try {
    const persisted: PersistedFrontendSession = {
      version: PERSISTENCE_VERSION,
      state: toAllowlistedProjection(state),
    }
    storage.setItem(FRONTEND_SESSION_STORAGE_KEY, JSON.stringify(persisted))
    return { ok: true }
  } catch {
    return { ok: false, reason: 'storage_unavailable' }
  }
}

const KNOWLEDGE_STATUSES: readonly KnowledgeStatus[] = [
  'UNKNOWN',
  'ASSUMPTION',
  'KNOWN',
  'CONFLICT',
]
const SOURCES = ['user', 'ai'] as const
const IDEA_STAGES: readonly IdeaStageChoice[] = [
  'I just have an idea',
  'I want to explore possibilities',
  'I already have a solution',
  'I need to make a decision',
]

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const isBoundedString = (value: unknown, maxLength: number): value is string =>
  typeof value === 'string' && value.length <= maxLength

const isNonBlankBoundedString = (value: unknown, maxLength: number): value is string =>
  isBoundedString(value, maxLength) && value.trim().length > 0

const isFrameValue = (value: unknown, kind: 'string' | 'list'): boolean => {
  if (!isRecord(value)) return false

  const validValue =
    kind === 'string'
      ? isBoundedString(value.value, MAX_FRAME_TEXT_LENGTH)
      : Array.isArray(value.value) &&
        value.value.length <= MAX_LIST_LENGTH &&
        value.value.every((item) => isNonBlankBoundedString(item, MAX_LIST_ITEM_LENGTH))

  return (
    validValue &&
    KNOWLEDGE_STATUSES.includes(value.status as KnowledgeStatus) &&
    SOURCES.includes(value.source as (typeof SOURCES)[number])
  )
}

const isFrameSchema = (value: unknown): value is FrameSchema =>
  isRecord(value) &&
  isFrameValue(value.target_user, 'string') &&
  isFrameValue(value.core_task, 'string') &&
  isFrameValue(value.desired_change, 'string') &&
  isFrameValue(value.hard_constraints, 'list') &&
  isFrameValue(value.success_metrics, 'list') &&
  isFrameValue(value.abandonment_criteria, 'list') &&
  isFrameValue(value.non_goals, 'list') &&
  isFrameValue(value.validation_horizon, 'string')

const isFrontendSessionState = (value: unknown): value is FrontendSessionState => {
  if (!isRecord(value)) return false
  if (
    value.sessionId !== undefined &&
    !isNonBlankBoundedString(value.sessionId, MAX_SESSION_ID_LENGTH)
  ) {
    return false
  }
  if (
    value.revision !== undefined &&
    (!Number.isSafeInteger(value.revision) || (value.revision as number) < 0)
  ) {
    return false
  }
  if (
    value.selectedIdeaStage !== undefined &&
    !IDEA_STAGES.includes(value.selectedIdeaStage as IdeaStageChoice)
  ) {
    return false
  }

  return (
    typeof value.route === 'string' &&
    ALLOWED_ROUTES.has(value.route) &&
    isBoundedString(value.idea, MAX_IDEA_LENGTH) &&
    Number.isInteger(value.currentFrame) &&
    (value.currentFrame as number) >= 0 &&
    (value.currentFrame as number) <= 5 &&
    isFrameSchema(value.frames)
  )
}

export const restoreFrontendSessionState = (storage: Storage): FrontendSessionState | null => {
  try {
    const raw = storage.getItem(FRONTEND_SESSION_STORAGE_KEY)
    if (raw === null) return null

    const parsed: unknown = JSON.parse(raw)
    if (!isRecord(parsed) || parsed.version !== PERSISTENCE_VERSION) return null
    if (!isFrontendSessionState(parsed.state)) return null
    return toAllowlistedProjection(parsed.state)
  } catch {
    return null
  }
}
