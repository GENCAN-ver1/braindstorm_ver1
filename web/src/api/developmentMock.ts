import type {
  BrainstormApi,
  BrainstormSession,
  BrainstormStage,
  CapabilityProvider,
  CapabilityRequest,
  CreateBrainstormRequest,
  FrameSchema,
  FrameValue,
  GovernorMode,
  GovernorStatus,
  HandoffContract,
  HumanGateDecision,
  MissingInputSubmission,
  StageStatus,
} from '../types/contracts'
import { apiError } from './errors'

const STORAGE_KEY = 'brainstorm.mock-governor.v1'
const PERSISTENCE_VERSION = 1

type MockPhase =
  | 'created'
  | 'needs_input'
  | 'awaiting_capability'
  | 'awaiting_human_gate'
  | 'committed'
  | 'parked'

interface MockSession {
  id: string
  revision: number
  mode: GovernorMode
  governorStatus: GovernorStatus
  frames: FrameSchema
  stages: BrainstormStage[]
  phase: MockPhase
  councilSkipped: boolean
  providers?: CapabilityProvider[]
}

type PersistedMockSession = Omit<MockSession, 'providers'>

interface MockSnapshot {
  version: typeof PERSISTENCE_VERSION
  nextId: number
  sessions: PersistedMockSession[]
}

const STAGE_DEFINITIONS: ReadonlyArray<{ id: string; label: string }> = [
  { id: 'route', label: 'Route' },
  { id: 'frame', label: 'Frame' },
  { id: 'diverge', label: 'Diverge' },
  { id: 'normalize', label: 'Normalize' },
  { id: 'challenge', label: 'Challenge' },
  { id: 'converge', label: 'Converge' },
  { id: 'capability', label: 'External capabilities' },
  { id: 'human-gate', label: 'Human gate' },
  { id: 'evaluator', label: 'Evaluator' },
]

const FRAME_KEYS = [
  'target_user',
  'core_task',
  'desired_change',
  'hard_constraints',
  'success_metrics',
  'abandonment_criteria',
  'non_goals',
  'validation_horizon',
] as const satisfies readonly (keyof FrameSchema)[]

type AnyFrameValue = FrameValue<string> | FrameValue<string[]>

const isMissingFrameValue = (frame: AnyFrameValue): boolean => {
  if (frame.status === 'UNKNOWN') return true
  return Array.isArray(frame.value)
    ? frame.value.length === 0 || frame.value.every((item) => item.trim().length === 0)
    : frame.value.trim().length === 0
}

export const findMissingFrameFields = (frames: FrameSchema): (keyof FrameSchema)[] =>
  FRAME_KEYS.filter((key) => isMissingFrameValue(frames[key]))

const freshStages = (): BrainstormStage[] =>
  STAGE_DEFINITIONS.map((stage) => ({ ...stage, status: 'pending' as StageStatus }))

const applyStageStatuses = (
  stages: BrainstormStage[],
  updates: Partial<Record<string, StageStatus>>,
): BrainstormStage[] =>
  stages.map((stage) =>
    updates[stage.id] !== undefined ? { ...stage, status: updates[stage.id]! } : stage,
  )

const toSession = (session: MockSession): BrainstormSession => ({
  id: session.id,
  revision: session.revision,
  mode: session.mode,
  governorStatus: session.governorStatus,
  frames: session.frames,
  stages: session.stages,
})

const readStorage = (): string | null => {
  if (typeof window === 'undefined') return null
  try {
    return window.sessionStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

const writeStorage = (value: string): void => {
  if (typeof window === 'undefined') return
  try {
    window.sessionStorage.setItem(STORAGE_KEY, value)
  } catch {
    // storage unavailable; the mock stays in-memory only
  }
}

const loadSnapshot = (): { nextId: number; sessions: Map<string, MockSession> } => {
  const sessions = new Map<string, MockSession>()
  let nextId = 1
  const raw = readStorage()
  if (raw) {
    try {
      const parsed: unknown = JSON.parse(raw)
      if (
        typeof parsed === 'object' &&
        parsed !== null &&
        (parsed as { version?: unknown }).version === PERSISTENCE_VERSION &&
        Array.isArray((parsed as { sessions?: unknown }).sessions)
      ) {
        const snapshot = parsed as MockSnapshot
        nextId = snapshot.nextId
        for (const item of snapshot.sessions) {
          sessions.set(item.id, { ...item, providers: undefined })
        }
      }
    } catch {
      // malformed snapshot: start empty
    }
  }
  return { nextId, sessions }
}

const saveSnapshot = (nextId: number, sessions: Map<string, MockSession>): void => {
  const persisted: PersistedMockSession[] = [...sessions.values()].map((session) => ({
    id: session.id,
    revision: session.revision,
    mode: session.mode,
    governorStatus: session.governorStatus,
    frames: session.frames,
    stages: session.stages,
    phase: session.phase,
    councilSkipped: session.councilSkipped,
  }))
  const snapshot: MockSnapshot = { version: PERSISTENCE_VERSION, nextId, sessions: persisted }
  writeStorage(JSON.stringify(snapshot))
}

const applyMissingInput = (session: MockSession, input: MissingInputSubmission): void => {
  session.frames = {
    ...session.frames,
    [input.field]: {
      value: input.value,
      status: input.status,
      source: 'user',
    },
  } as FrameSchema
}

const advanceToCapability = (session: MockSession): void => {
  session.governorStatus = 'EXPLORE'
  session.phase = 'awaiting_capability'
  session.stages = applyStageStatuses(session.stages, {
    route: 'complete',
    frame: 'complete',
    diverge: 'complete',
    normalize: 'complete',
    challenge: 'complete',
    converge: 'complete',
    capability: 'pending',
    'human-gate': 'pending',
    evaluator: 'pending',
  })
}

const advanceToHumanGate = (session: MockSession, capabilityStatus: StageStatus): void => {
  session.governorStatus = 'ITERATE'
  session.phase = 'awaiting_human_gate'
  session.stages = applyStageStatuses(session.stages, {
    capability: capabilityStatus,
    'human-gate': 'pending',
    evaluator: 'pending',
  })
}

const validateProviders = (request: CapabilityRequest): void => {
  if (request.outcome !== 'enable') return
  for (const provider of request.providers) {
    const apiKey = provider.apiKey as unknown as string
    if (
      provider.name.trim().length === 0 ||
      provider.baseUrl.trim().length === 0 ||
      provider.model.trim().length === 0 ||
      apiKey.trim().length === 0
    ) {
      throw apiError(
        'VALIDATION_FAILURE',
        'Every provider needs a name, base URL, model, and API key.',
        { retryable: false },
      )
    }
    if (provider.name === 'failing-provider') {
      throw apiError('PROVIDER_FAILURE', `Provider "${provider.name}" failed to respond.`, {
        retryable: true,
      })
    }
  }
}

const buildHandoff = (session: MockSession): HandoffContract => {
  const { frames } = session
  const text = (frame: FrameValue<string>): string => frame.value
  const list = (frame: FrameValue<string[]>): string => frame.value.join('; ')
  return {
    problem_frame: [
      `target_user: ${text(frames.target_user)}`,
      `core_task: ${text(frames.core_task)}`,
      `desired_change: ${text(frames.desired_change)}`,
      `hard_constraints: ${list(frames.hard_constraints)}`,
      `success_metrics: ${list(frames.success_metrics)}`,
      `abandonment_criteria: ${list(frames.abandonment_criteria)}`,
      `non_goals: ${list(frames.non_goals)}`,
      `validation_horizon: ${text(frames.validation_horizon)}`,
    ].join('\n'),
    locked_decisions: [`mode: ${session.mode}`],
    open_questions: [],
    non_goals: [...frames.non_goals.value],
    acceptance_criteria: [],
    evidence_summary: ['Development simulation — no real Governor evidence'],
    recommended_next_action: 'Proceed to implementation review (simulation)',
  }
}

export function createDevelopmentMock(): BrainstormApi {
  return {
    async getSession(sessionId: string): Promise<BrainstormSession> {
      const { sessions } = loadSnapshot()
      const session = sessions.get(sessionId)
      if (!session) throw apiError('VALIDATION_FAILURE', 'Session not found.', { retryable: false })
      return toSession(session)
    },

    async createSession(request: CreateBrainstormRequest): Promise<BrainstormSession> {
      if (request.idea.trim().length === 0) {
        throw apiError('VALIDATION_FAILURE', 'Idea must not be blank.', {
          field: 'idea',
          retryable: false,
        })
      }
      const { nextId, sessions } = loadSnapshot()
      const id = `session-${nextId}`
      const session: MockSession = {
        id,
        revision: 0,
        mode: request.mode,
        governorStatus: 'NEEDS_INPUT',
        frames: request.frames,
        stages: freshStages(),
        phase: 'created',
        councilSkipped: false,
      }
      sessions.set(id, session)
      saveSnapshot(nextId + 1, sessions)
      return toSession(session)
    },

    async saveFrames(
      sessionId: string,
      revision: number,
      frames: FrameSchema,
    ): Promise<BrainstormSession> {
      const { nextId, sessions } = loadSnapshot()
      const session = sessions.get(sessionId)
      if (!session) throw apiError('VALIDATION_FAILURE', 'Session not found.', { retryable: false })
      if (session.revision !== revision) {
        throw apiError(
          'REVISION_CONFLICT',
          `Expected revision ${session.revision}, received ${revision}.`,
          { retryable: true },
        )
      }
      session.frames = frames
      session.revision += 1
      saveSnapshot(nextId, sessions)
      return toSession(session)
    },

    async startRun(sessionId: string, revision: number): Promise<BrainstormSession> {
      const { nextId, sessions } = loadSnapshot()
      const session = sessions.get(sessionId)
      if (!session) throw apiError('VALIDATION_FAILURE', 'Session not found.', { retryable: false })
      if (
        session.phase !== 'created' &&
        session.revision === 1 &&
        revision === session.revision - 1
      ) {
        return toSession(session)
      }
      if (session.revision !== revision) {
        throw apiError(
          'REVISION_CONFLICT',
          `Expected revision ${session.revision}, received ${revision}.`,
          { retryable: true },
        )
      }
      if (session.phase === 'created') {
        session.revision += 1
        if (findMissingFrameFields(session.frames).length > 0) {
          session.governorStatus = 'NEEDS_INPUT'
          session.phase = 'needs_input'
          session.stages = applyStageStatuses(session.stages, {
            route: 'complete',
            frame: 'needs_input',
          })
        } else {
          advanceToCapability(session)
        }
      }
      saveSnapshot(nextId, sessions)
      return toSession(session)
    },

    async resumeRun(
      sessionId: string,
      revision: number,
      input: MissingInputSubmission,
    ): Promise<BrainstormSession> {
      const { nextId, sessions } = loadSnapshot()
      const session = sessions.get(sessionId)
      if (!session) throw apiError('VALIDATION_FAILURE', 'Session not found.', { retryable: false })
      if (session.revision !== revision) {
        throw apiError(
          'REVISION_CONFLICT',
          `Expected revision ${session.revision}, received ${revision}.`,
          { retryable: true },
        )
      }
      if (session.phase !== 'needs_input') {
        throw apiError('VALIDATION_FAILURE', 'Session is not waiting for input.', {
          retryable: false,
        })
      }
      applyMissingInput(session, input)
      session.revision += 1
      if (findMissingFrameFields(session.frames).length > 0) {
        session.governorStatus = 'NEEDS_INPUT'
      } else {
        advanceToCapability(session)
      }
      saveSnapshot(nextId, sessions)
      return toSession(session)
    },

    async configureCapabilities(
      sessionId: string,
      revision: number,
      request: CapabilityRequest,
    ): Promise<BrainstormSession> {
      const { nextId, sessions } = loadSnapshot()
      const session = sessions.get(sessionId)
      if (!session) throw apiError('VALIDATION_FAILURE', 'Session not found.', { retryable: false })
      if (session.revision !== revision) {
        throw apiError(
          'REVISION_CONFLICT',
          `Expected revision ${session.revision}, received ${revision}.`,
          { retryable: true },
        )
      }
      if (session.phase !== 'awaiting_capability') {
        throw apiError('VALIDATION_FAILURE', 'Session is not awaiting a capability decision.', {
          retryable: false,
        })
      }
      session.revision += 1
      if (request.outcome === 'skip') {
        session.councilSkipped = true
        session.providers = undefined
        advanceToHumanGate(session, 'skipped')
      } else {
        validateProviders(request)
        if (request.capability === 'council') {
          const names = request.providers.map((provider) => provider.name)
          if (new Set(names).size !== names.length) {
            throw apiError(
              'VALIDATION_FAILURE',
              'Council requires providers with distinct names.',
              { retryable: false },
            )
          }
        }
        session.providers = request.providers
        session.councilSkipped = false
        advanceToHumanGate(session, 'complete')
      }
      saveSnapshot(nextId, sessions)
      return toSession(session)
    },

    async submitHumanGate(
      sessionId: string,
      revision: number,
      decision: HumanGateDecision,
    ): Promise<BrainstormSession> {
      const { nextId, sessions } = loadSnapshot()
      const session = sessions.get(sessionId)
      if (!session) throw apiError('VALIDATION_FAILURE', 'Session not found.', { retryable: false })
      if (session.revision !== revision) {
        throw apiError(
          'REVISION_CONFLICT',
          `Expected revision ${session.revision}, received ${revision}.`,
          { retryable: true },
        )
      }
      if (session.phase !== 'awaiting_human_gate') {
        throw apiError('VALIDATION_FAILURE', 'Session is not awaiting a human gate decision.', {
          retryable: false,
        })
      }
      session.revision += 1
      if (decision.kind === 'confirm') {
        session.governorStatus = 'COMMIT'
        session.phase = 'committed'
        session.stages = applyStageStatuses(session.stages, {
          'human-gate': 'complete',
          evaluator: 'complete',
        })
      } else if (decision.kind === 'request_iteration') {
        session.governorStatus = 'ITERATE'
        session.stages = applyStageStatuses(session.stages, { 'human-gate': 'needs_input' })
      } else {
        applyMissingInput(session, decision.input)
        if (findMissingFrameFields(session.frames).length > 0) {
          session.governorStatus = 'NEEDS_INPUT'
          session.phase = 'needs_input'
        } else {
          advanceToHumanGate(session, 'complete')
        }
      }
      saveSnapshot(nextId, sessions)
      return toSession(session)
    },

    async getHandoff(sessionId: string): Promise<HandoffContract | null> {
      const { sessions } = loadSnapshot()
      const session = sessions.get(sessionId)
      if (!session || session.phase !== 'committed') return null
      return buildHandoff(session)
    },
  }
}

export const isDevelopmentSimulation = true
export const createSelectedApi = createDevelopmentMock
