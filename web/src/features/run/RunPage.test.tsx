import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import { completeFrames, renderApp, resetGovernor, seedSession } from '../../test/testUtils'

beforeEach(() => resetGovernor())

describe('RunPage', () => {
  it('shows the stages and a needs-input panel for an incomplete session', async () => {
    const frames = completeFrames()
    frames.core_task = { value: '', status: 'UNKNOWN', source: 'user' }
    await seedSession(frames)
    renderApp(['/run'])

    expect(await screen.findByText('Provide missing information')).toBeInTheDocument()
    expect(screen.getByText('Needs input')).toBeInTheDocument()
    expect(screen.getByText('Frame: Needs input')).toBeInTheDocument()
  })

  it('resumes to the capability decision after supplying the missing input', async () => {
    const user = userEvent.setup()
    const frames = completeFrames()
    frames.core_task = { value: '', status: 'UNKNOWN', source: 'user' }
    await seedSession(frames)
    renderApp(['/run'])

    await screen.findByText('Provide missing information')
    await user.type(screen.getByLabelText('Core task'), 'Shape ideas')
    await user.click(screen.getByRole('button', { name: /resume/i }))

    expect(
      await screen.findByRole('button', { name: /configure external capabilities/i }),
    ).toBeInTheDocument()
  })

  it('offers the capability decision for a complete session', async () => {
    await seedSession(completeFrames())
    renderApp(['/run'])

    expect(
      await screen.findByRole('button', { name: /configure external capabilities/i }),
    ).toBeInTheDocument()
  })
})
