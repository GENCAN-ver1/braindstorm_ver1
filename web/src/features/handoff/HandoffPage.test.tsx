import { screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import {
  completeFrames,
  renderApp,
  resetGovernor,
  seedCommittedSession,
  seedSession,
} from '../../test/testUtils'

beforeEach(() => resetGovernor())

describe('HandoffPage', () => {
  it('does not render a final handoff before COMMIT', async () => {
    await seedSession(completeFrames(), '/handoff')
    renderApp(['/handoff'])

    expect(
      await screen.findByText(/only available after the governor commits/i),
    ).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /final handoff/i })).not.toBeInTheDocument()
  })

  it('renders the final handoff after COMMIT', async () => {
    await seedCommittedSession()
    renderApp(['/handoff'])

    expect(await screen.findByRole('heading', { name: /final handoff/i })).toBeInTheDocument()
    expect(screen.getByText(/no real governor evidence/i)).toBeInTheDocument()
  })
})
