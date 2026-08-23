import { beforeEach, describe, expect, it } from 'vitest'

import type { FrontendSessionState } from '../types/contracts'
import {
  FRONTEND_SESSION_STORAGE_KEY,
  persistFrontendSessionState,
  restoreFrontendSessionState,
} from './sessionPersistence'

const sessionState = (): FrontendSessionState => ({
  sessionId: 'session-1',
  revision: 3,
  route: '/frames/success',
  idea: 'A guided Brainstorm web host',
  selectedIdeaStage: 'I just have an idea',
  currentFrame: 3,
  frames: {
    target_user: { value: 'Product teams', status: 'KNOWN', source: 'user' },
    core_task: { value: 'Shape ideas', status: 'KNOWN', source: 'user' },
    desired_change: { value: 'Decide with evidence', status: 'ASSUMPTION', source: 'ai' },
    hard_constraints: { value: ['Local only'], status: 'KNOWN', source: 'user' },
    success_metrics: { value: ['Complete flow'], status: 'KNOWN', source: 'user' },
    abandonment_criteria: { value: ['No legal path'], status: 'KNOWN', source: 'user' },
    non_goals: { value: ['Deploy'], status: 'KNOWN', source: 'user' },
    validation_horizon: { value: 'One session', status: 'KNOWN', source: 'user' },
  },
})

describe('frontend session persistence', () => {
  beforeEach(() => sessionStorage.clear())

  it('round-trips a versioned allowlisted non-secret projection', () => {
    const state = sessionState()

    expect(persistFrontendSessionState(sessionStorage, state)).toEqual({ ok: true })

    expect(restoreFrontendSessionState(sessionStorage)).toEqual(state)
    expect(JSON.parse(sessionStorage.getItem(FRONTEND_SESSION_STORAGE_KEY) ?? '{}')).toMatchObject({
      version: 1,
      state: { sessionId: 'session-1', revision: 3 },
    })
  })

  it('never serialises provider keys, authorization secrets, or unknown extra fields', () => {
    const taintedState = {
      ...sessionState(),
      providerApiKey: 'fake-provider-key-DO-NOT-STORE',
      authorizationSecret: 'fake-authorization-secret-DO-NOT-STORE',
      nestedSecret: { apiKey: 'fake-nested-key-DO-NOT-STORE' },
    } as FrontendSessionState

    persistFrontendSessionState(sessionStorage, taintedState)

    const stored = sessionStorage.getItem(FRONTEND_SESSION_STORAGE_KEY) ?? ''
    expect(stored).not.toContain('fake-provider-key-DO-NOT-STORE')
    expect(stored).not.toContain('fake-authorization-secret-DO-NOT-STORE')
    expect(stored).not.toContain('fake-nested-key-DO-NOT-STORE')
    expect(JSON.parse(stored).state).not.toHaveProperty('providerApiKey')
  })

  it('rejects stale or malformed projections instead of trusting them', () => {
    sessionStorage.setItem(
      FRONTEND_SESSION_STORAGE_KEY,
      JSON.stringify({ version: 0, state: sessionState() }),
    )
    expect(restoreFrontendSessionState(sessionStorage)).toBeNull()

    sessionStorage.setItem(FRONTEND_SESSION_STORAGE_KEY, '{not-json')
    expect(restoreFrontendSessionState(sessionStorage)).toBeNull()
  })

  it.each([
    ['negative revision', { ...sessionState(), revision: -1 }],
    ['fractional revision', { ...sessionState(), revision: 1.5 }],
    ['unsafe revision', { ...sessionState(), revision: Number.MAX_SAFE_INTEGER + 1 }],
    ['negative frame index', { ...sessionState(), currentFrame: -1 }],
    ['out-of-range frame index', { ...sessionState(), currentFrame: 6 }],
    ['fractional frame index', { ...sessionState(), currentFrame: 1.5 }],
    ['unknown route', { ...sessionState(), route: '/admin' }],
    ['unsafe route', { ...sessionState(), route: 'javascript:alert(1)' }],
    ['blank session id', { ...sessionState(), sessionId: '   ' }],
    ['oversized session id', { ...sessionState(), sessionId: 's'.repeat(129) }],
  ])('rejects %s in restored storage', (_caseName, state) => {
    sessionStorage.setItem(
      FRONTEND_SESSION_STORAGE_KEY,
      JSON.stringify({ version: 1, state }),
    )

    expect(restoreFrontendSessionState(sessionStorage)).toBeNull()
  })

  it('rejects oversized strings, oversized lists, and blank or oversized list items', () => {
    const oversizedFrame = sessionState()
    oversizedFrame.frames.target_user.value = 'x'.repeat(2001)
    const oversizedList = sessionState()
    oversizedList.frames.non_goals.value = Array.from({ length: 51 }, (_, index) => `goal-${index}`)
    const blankListItem = sessionState()
    blankListItem.frames.success_metrics.value = ['   ']
    const oversizedListItem = sessionState()
    oversizedListItem.frames.hard_constraints.value = ['x'.repeat(501)]

    for (const state of [
      { ...sessionState(), idea: 'x'.repeat(4001) },
      oversizedFrame,
      oversizedList,
      blankListItem,
      oversizedListItem,
    ]) {
      sessionStorage.setItem(
        FRONTEND_SESSION_STORAGE_KEY,
        JSON.stringify({ version: 1, state }),
      )
      expect(restoreFrontendSessionState(sessionStorage)).toBeNull()
    }
  })

  it.each(['SecurityError', 'QuotaExceededError'])('returns a failure result for %s', (name) => {
    const unavailableStorage = {
      setItem: () => {
        throw new DOMException('Storage unavailable', name)
      },
    } as unknown as Storage

    expect(persistFrontendSessionState(unavailableStorage, sessionState())).toEqual({
      ok: false,
      reason: 'storage_unavailable',
    })
  })

  it('returns null when storage access is blocked during restore', () => {
    const unavailableStorage = {
      getItem: () => {
        throw new DOMException('Storage unavailable', 'SecurityError')
      },
    } as unknown as Storage

    expect(restoreFrontendSessionState(unavailableStorage)).toBeNull()
  })
})
