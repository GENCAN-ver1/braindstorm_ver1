import { beforeEach, describe, expect, it } from 'vitest'
import type {
  CapabilityProvider,
  CreateBrainstormRequest,
  EphemeralProviderSecret,
  FrameSchema,
  FrameValue,
} from '../types/contracts'
import { createDevelopmentMock } from './developmentMock'

const stringValue = (value: string): FrameValue<string> => ({
  value,
  status: 'KNOWN',
  source: 'user',
})

const listValue = (value: string[]): FrameValue<string[]> => ({
  value,
  status: 'KNOWN',
  source: 'user',
})

const completeFrames = (): FrameSchema => ({
  target_user: stringValue('Product teams'),
  core_task: stringValue('Shape ideas'),
  desired_change: stringValue('Decide with evidence'),
  hard_constraints: listValue(['Local only']),
  success_metrics: listValue(['A clear handoff']),
  abandonment_criteria: listValue(['No viable path']),
  non_goals: listValue(['Deployment']),
  validation_horizon: stringValue('One session'),
})

const makeRequest = (frames: FrameSchema): CreateBrainstormRequest => ({
  idea: 'A guided brainstorm host',
  mode: 'Shape',
  frames,
})

const provider = (name: string): CapabilityProvider => ({
  name,
  baseUrl: 'https://provider.example.test',
  model: 'test-model',
  apiKey: 'test-key' as EphemeralProviderSecret,
})

beforeEach(() => sessionStorage.clear())

describe('developmentMock state machine', () => {
  it('runs a complete frame set to the capability decision', async () => {
    const api = createDevelopmentMock()
    const created = await api.createSession(makeRequest(completeFrames()))
    const run = await api.startRun(created.id, created.revision)
    expect(run.governorStatus).toBe('EXPLORE')
    expect(run.revision).toBeGreaterThan(created.revision)
  })

  it('stops at NEEDS_INPUT for incomplete frames and resumes within the same lineage', async () => {
    const api = createDevelopmentMock()
    const frames = completeFrames()
    frames.core_task = { value: '', status: 'UNKNOWN', source: 'user' }
    const created = await api.createSession(makeRequest(frames))
    const run = await api.startRun(created.id, created.revision)
    expect(run.governorStatus).toBe('NEEDS_INPUT')
    expect(run.id).toBe(created.id)

    const resumed = await api.resumeRun(run.id, run.revision, {
      field: 'core_task',
      value: 'Shape ideas',
      status: 'KNOWN',
    })
    expect(resumed.id).toBe(created.id)
    expect(resumed.governorStatus).toBe('EXPLORE')
  })

  it('supports the standard skip path', async () => {
    const api = createDevelopmentMock()
    const created = await api.createSession(makeRequest(completeFrames()))
    const run = await api.startRun(created.id, created.revision)
    const configured = await api.configureCapabilities(run.id, run.revision, {
      capability: 'council',
      outcome: 'skip',
      authorized: false,
    })
    expect(configured.governorStatus).toBe('ITERATE')
  })

  it('rejects a Council with non-distinct provider names', async () => {
    const api = createDevelopmentMock()
    const created = await api.createSession(makeRequest(completeFrames()))
    const run = await api.startRun(created.id, created.revision)
    await expect(
      api.configureCapabilities(run.id, run.revision, {
        capability: 'council',
        outcome: 'enable',
        authorized: true,
        providers: [provider('same'), provider('same')],
      }),
    ).rejects.toMatchObject({ code: 'VALIDATION_FAILURE' })
  })

  it('enables the Council with two distinct providers and explicit authorization', async () => {
    const api = createDevelopmentMock()
    const created = await api.createSession(makeRequest(completeFrames()))
    const run = await api.startRun(created.id, created.revision)
    const configured = await api.configureCapabilities(run.id, run.revision, {
      capability: 'council',
      outcome: 'enable',
      authorized: true,
      providers: [provider('one'), provider('two')],
    })
    expect(configured.governorStatus).toBe('ITERATE')
  })

  it('surfaces a provider failure', async () => {
    const api = createDevelopmentMock()
    const created = await api.createSession(makeRequest(completeFrames()))
    const run = await api.startRun(created.id, created.revision)
    await expect(
      api.configureCapabilities(run.id, run.revision, {
        capability: 'council',
        outcome: 'enable',
        authorized: true,
        providers: [provider('failing-provider'), provider('two')],
      }),
    ).rejects.toMatchObject({ code: 'PROVIDER_FAILURE' })
  })

  it('returns a handoff only after COMMIT', async () => {
    const api = createDevelopmentMock()
    const created = await api.createSession(makeRequest(completeFrames()))
    const run = await api.startRun(created.id, created.revision)
    expect(await api.getHandoff(created.id)).toBeNull()

    const configured = await api.configureCapabilities(run.id, run.revision, {
      capability: 'council',
      outcome: 'skip',
      authorized: false,
    })
    const committed = await api.submitHumanGate(configured.id, configured.revision, {
      kind: 'confirm',
    })
    expect(committed.governorStatus).toBe('COMMIT')

    const handoff = await api.getHandoff(created.id)
    expect(handoff).not.toBeNull()
    expect(handoff?.locked_decisions).toContain('mode: Shape')
  })

  it('rejects stale revisions', async () => {
    const api = createDevelopmentMock()
    const created = await api.createSession(makeRequest(completeFrames()))
    await expect(api.startRun(created.id, created.revision + 5)).rejects.toMatchObject({
      code: 'REVISION_CONFLICT',
    })
  })
})
