import { afterEach, describe, expect, it, vi } from 'vitest'
import { createHttpApi } from './httpApi'
import type { CreateBrainstormRequest } from '../types/contracts'

const unknownString = { value: '', status: 'UNKNOWN' as const, source: 'user' as const }
const unknownList = { value: [] as string[], status: 'UNKNOWN' as const, source: 'user' as const }

const request: CreateBrainstormRequest = {
  idea: 'A governed idea',
  mode: 'Spark',
  frames: {
    target_user: unknownString,
    core_task: unknownString,
    desired_change: unknownString,
    hard_constraints: unknownList,
    success_metrics: unknownList,
    abandonment_criteria: unknownList,
    non_goals: unknownList,
    validation_horizon: unknownString,
  },
}

const session = {
  id: 'session-0123456789abcdef0123456789abcdef',
  revision: 0,
  mode: 'Spark',
  governorStatus: 'NEEDS_INPUT',
  frames: request.frames,
  stages: [],
  review: null,
}

afterEach(() => vi.restoreAllMocks())

describe('HTTP Brainstorm API', () => {
  it('uses the same-origin typed session route without credentials', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(session), {
        status: 201,
        headers: { 'Content-Type': 'application/json' },
      }),
    )

    await expect(createHttpApi().createSession(request)).resolves.toEqual(session)
    const [url, options] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/sessions')
    expect(options).toMatchObject({ method: 'POST', credentials: 'same-origin' })
    expect(JSON.stringify(options)).not.toMatch(/api.?key|authorization|bearer/i)
  })

  it('preserves safe typed provider failures', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ code: 'PROVIDER_FAILURE', message: 'provider request failed', retryable: true }),
        { status: 502, headers: { 'Content-Type': 'application/json' } },
      ),
    )

    await expect(createHttpApi().startRun(session.id, 0)).rejects.toMatchObject({
      code: 'PROVIDER_FAILURE',
      retryable: true,
    })
  })

  it('rejects malformed successful host responses', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ status: 'looks-successful' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )

    await expect(createHttpApi().getSession(session.id)).rejects.toMatchObject({
      code: 'PROVIDER_FAILURE',
    })
  })

  it('returns null only for an explicit non-committed handoff', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('null', { status: 200, headers: { 'Content-Type': 'application/json' } }),
    )
    await expect(createHttpApi().getHandoff(session.id)).resolves.toBeNull()
  })
})
