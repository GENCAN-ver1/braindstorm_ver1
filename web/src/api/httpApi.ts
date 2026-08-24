import type {
  BrainstormApi,
  BrainstormApiError,
  BrainstormSession,
  CapabilityRequest,
  CreateBrainstormRequest,
  FrameSchema,
  HandoffContract,
  HumanGateDecision,
  MissingInputSubmission,
} from '../types/contracts'

const API_ROOT = '/api/v1'
const TIMEOUT_MS = 75_000

const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const parseSession = (value: unknown): BrainstormSession => {
  if (
    !isObject(value) ||
    typeof value.id !== 'string' ||
    typeof value.revision !== 'number' ||
    typeof value.mode !== 'string' ||
    typeof value.governorStatus !== 'string' ||
    !isObject(value.frames) ||
    !Array.isArray(value.stages)
  ) {
    throw apiFailure('PROVIDER_FAILURE', 'The host returned an invalid session.', true)
  }
  return value as unknown as BrainstormSession
}

const apiFailure = (
  code: BrainstormApiError['code'],
  message: string,
  retryable: boolean,
  field?: string,
): BrainstormApiError => ({ code, message, retryable, field })

const request = async <T>(
  path: string,
  options: { method?: 'GET' | 'POST' | 'PUT'; body?: unknown } = {},
): Promise<T> => {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), TIMEOUT_MS)
  try {
    const response = await fetch(`${API_ROOT}${path}`, {
      method: options.method ?? 'GET',
      credentials: 'same-origin',
      headers: options.body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: controller.signal,
    })
    let payload: unknown
    try {
      payload = await response.json()
    } catch {
      throw apiFailure('PROVIDER_FAILURE', 'The host returned an invalid response.', true)
    }
    if (!response.ok) {
      if (isObject(payload) && typeof payload.code === 'string' && typeof payload.message === 'string') {
        throw payload as unknown as BrainstormApiError
      }
      throw apiFailure('PROVIDER_FAILURE', 'The host could not complete the request.', response.status >= 500)
    }
    return payload as T
  } catch (error) {
    if (isObject(error) && typeof error.code === 'string') throw error
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw apiFailure('TIMEOUT', 'The host request timed out.', true)
    }
    throw apiFailure('NETWORK_FAILURE', 'Could not reach the local Brainstorm host.', true)
  } finally {
    window.clearTimeout(timer)
  }
}

export function createHttpApi(): BrainstormApi {
  return {
    async getSession(sessionId) {
      return parseSession(await request(`/sessions/${encodeURIComponent(sessionId)}`))
    },
    async createSession(input: CreateBrainstormRequest) {
      return parseSession(await request('/sessions', { method: 'POST', body: input }))
    },
    async saveFrames(sessionId: string, revision: number, frames: FrameSchema) {
      return parseSession(
        await request(`/sessions/${encodeURIComponent(sessionId)}/frames`, {
          method: 'PUT',
          body: { revision, frames },
        }),
      )
    },
    async startRun(sessionId: string, revision: number) {
      return parseSession(
        await request(`/sessions/${encodeURIComponent(sessionId)}/run`, {
          method: 'POST',
          body: { revision },
        }),
      )
    },
    async resumeRun(sessionId: string, revision: number, input: MissingInputSubmission) {
      return parseSession(
        await request(`/sessions/${encodeURIComponent(sessionId)}/resume`, {
          method: 'POST',
          body: { revision, input },
        }),
      )
    },
    async configureCapabilities(sessionId: string, revision: number, capability: CapabilityRequest) {
      return parseSession(
        await request(`/sessions/${encodeURIComponent(sessionId)}/capabilities`, {
          method: 'POST',
          body: { revision, request: capability },
        }),
      )
    },
    async submitHumanGate(sessionId: string, revision: number, decision: HumanGateDecision) {
      return parseSession(
        await request(`/sessions/${encodeURIComponent(sessionId)}/human-gate`, {
          method: 'POST',
          body: { revision, decision },
        }),
      )
    },
    async getHandoff(sessionId: string) {
      const value = await request<unknown>(`/sessions/${encodeURIComponent(sessionId)}/handoff`)
      if (value === null) return null
      if (!isObject(value)) throw apiFailure('PROVIDER_FAILURE', 'The host returned an invalid handoff.', true)
      return value as unknown as HandoffContract
    },
  }
}

export const isDevelopmentSimulation = false
export const createSelectedApi = createHttpApi
