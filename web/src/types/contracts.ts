export type GovernorMode = 'Shape' | 'Spark' | 'Stress' | 'Decide'

export type KnowledgeStatus = 'UNKNOWN' | 'ASSUMPTION' | 'KNOWN' | 'CONFLICT'

export type GovernorStatus =
  | 'NEEDS_INPUT'
  | 'RESEARCH_REQUIRED'
  | 'EXPLORE'
  | 'ITERATE'
  | 'PARK'
  | 'COMMIT'

export type StageStatus =
  | 'pending'
  | 'running'
  | 'complete'
  | 'needs_input'
  | 'blocked'
  | 'skipped'
  | 'failed'

export type IdeaStageChoice =
  | 'I just have an idea'
  | 'I want to explore possibilities'
  | 'I already have a solution'
  | 'I need to make a decision'

export type FrameName =
  | 'Who & Job'
  | 'Desired Change'
  | 'Constraints'
  | 'Success'
  | 'Failure Boundary'
  | 'Scope & Validation'

export interface FrameValue<T> {
  value: T
  status: KnowledgeStatus
  source: 'user' | 'ai'
}

export interface FrameSchema {
  target_user: FrameValue<string>
  core_task: FrameValue<string>
  desired_change: FrameValue<string>
  hard_constraints: FrameValue<string[]>
  success_metrics: FrameValue<string[]>
  abandonment_criteria: FrameValue<string[]>
  non_goals: FrameValue<string[]>
  validation_horizon: FrameValue<string>
}

export interface FrameValidationError {
  field: keyof FrameSchema
  message: string
}

export interface BrainstormStage {
  id: string
  label: string
  status: StageStatus
}

export interface BrainstormSession {
  id: string
  revision: number
  mode: GovernorMode
  governorStatus: GovernorStatus
  frames: FrameSchema
  stages: BrainstormStage[]
}

export interface FrontendSessionState {
  sessionId?: string
  revision?: number
  route: string
  idea: string
  selectedIdeaStage?: IdeaStageChoice
  currentFrame: number
  frames: FrameSchema
}

export interface CreateBrainstormRequest {
  idea: string
  mode: GovernorMode
  frames: FrameSchema
}

export type MissingInputSubmission = {
  [Field in keyof FrameSchema]: {
    field: Field
    value: FrameSchema[Field]['value']
    status: Exclude<KnowledgeStatus, 'UNKNOWN'>
  }
}[keyof FrameSchema]

declare const ephemeralProviderSecret: unique symbol

export type EphemeralProviderSecret = string & {
  readonly [ephemeralProviderSecret]: true
}

export interface CapabilityProvider {
  name: string
  baseUrl: string
  model: string
  apiKey: EphemeralProviderSecret
}

type CapabilityName = 'research' | 'council' | 'evaluator'

interface SkippedCapabilityRequest {
  capability: CapabilityName
  outcome: 'skip'
  authorized: false
  providers?: never
}

interface EnabledCouncilRequest {
  capability: 'council'
  outcome: 'enable'
  authorized: true
  providers: [CapabilityProvider, CapabilityProvider, ...CapabilityProvider[]]
}

interface EnabledSingleProviderCapabilityRequest {
  capability: 'research' | 'evaluator'
  outcome: 'enable'
  authorized: true
  providers: [CapabilityProvider, ...CapabilityProvider[]]
}

export type CapabilityRequest =
  | SkippedCapabilityRequest
  | EnabledCouncilRequest
  | EnabledSingleProviderCapabilityRequest

export type HumanGateDecision =
  | { kind: 'confirm' }
  | { kind: 'request_iteration'; feedback: string }
  | { kind: 'provide_missing_input'; input: MissingInputSubmission }

export interface HandoffContract {
  problem_frame: string
  locked_decisions: string[]
  open_questions: string[]
  non_goals: string[]
  acceptance_criteria: string[]
  evidence_summary: string[]
  recommended_next_action: string
}

export interface BrainstormApi {
  createSession(request: CreateBrainstormRequest): Promise<BrainstormSession>
  saveFrames(sessionId: string, revision: number, frames: FrameSchema): Promise<BrainstormSession>
  startRun(sessionId: string, revision: number): Promise<BrainstormSession>
  resumeRun(
    sessionId: string,
    revision: number,
    input: MissingInputSubmission,
  ): Promise<BrainstormSession>
  configureCapabilities(
    sessionId: string,
    revision: number,
    request: CapabilityRequest,
  ): Promise<BrainstormSession>
  submitHumanGate(
    sessionId: string,
    revision: number,
    decision: HumanGateDecision,
  ): Promise<BrainstormSession>
  getHandoff(sessionId: string): Promise<HandoffContract | null>
}

export type BrainstormApiErrorCode =
  | 'TIMEOUT'
  | 'NETWORK_FAILURE'
  | 'UNAUTHORIZED'
  | 'FORBIDDEN'
  | 'REVISION_CONFLICT'
  | 'PROVIDER_FAILURE'
  | 'VALIDATION_FAILURE'

export interface BrainstormApiError {
  code: BrainstormApiErrorCode
  message: string
  field?: string
  retryable: boolean
}
