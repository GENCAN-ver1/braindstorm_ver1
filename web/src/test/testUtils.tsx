import { StrictMode } from 'react'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type {
  BrainstormSession,
  CreateBrainstormRequest,
  FrameSchema,
  FrameValue,
  GovernorMode,
} from '../types/contracts'
import { getBrainstormApi, resetBrainstormApi } from '../api/client'
import { persistFrontendSessionState } from '../state/sessionPersistence'
import { App } from '../app/App'

export const stringValue = (value: string): FrameValue<string> => ({
  value,
  status: 'KNOWN',
  source: 'user',
})

export const listValue = (value: string[]): FrameValue<string[]> => ({
  value,
  status: 'KNOWN',
  source: 'user',
})

export const completeFrames = (): FrameSchema => ({
  target_user: stringValue('Product teams'),
  core_task: stringValue('Shape ideas'),
  desired_change: stringValue('Decide with evidence'),
  hard_constraints: listValue(['Local only']),
  success_metrics: listValue(['A clear handoff']),
  abandonment_criteria: listValue(['No viable path']),
  non_goals: listValue(['Deployment']),
  validation_horizon: stringValue('One session'),
})

export const resetGovernor = (): void => {
  sessionStorage.clear()
  resetBrainstormApi()
}

export const makeRequest = (
  frames: FrameSchema,
  mode: GovernorMode = 'Shape',
): CreateBrainstormRequest => ({
  idea: 'A guided brainstorm host',
  mode,
  frames,
})

export async function seedSession(
  frames: FrameSchema,
  route = '/run',
): Promise<BrainstormSession> {
  const api = getBrainstormApi()
  const created = await api.createSession(makeRequest(frames))
  const run = await api.startRun(created.id, created.revision)
  persistFrontendSessionState(sessionStorage, {
    sessionId: run.id,
    revision: run.revision,
    route,
    idea: 'A guided brainstorm host',
    currentFrame: 0,
    frames: run.frames,
  })
  return run
}

export async function seedCommittedSession(): Promise<void> {
  const api = getBrainstormApi()
  const created = await api.createSession(makeRequest(completeFrames()))
  const run = await api.startRun(created.id, created.revision)
  const configured = await api.configureCapabilities(run.id, run.revision, {
    capability: 'council',
    outcome: 'skip',
    authorized: false,
  })
  const committed = await api.submitHumanGate(configured.id, configured.revision, {
    kind: 'confirm',
  })
  persistFrontendSessionState(sessionStorage, {
    sessionId: committed.id,
    revision: committed.revision,
    route: '/handoff',
    idea: 'A guided brainstorm host',
    currentFrame: 0,
    frames: committed.frames,
  })
}

export const renderApp = (initialEntries: string[] = ['/']) =>
  render(
    <StrictMode>
      <MemoryRouter initialEntries={initialEntries}>
        <App />
      </MemoryRouter>
    </StrictMode>,
  )
