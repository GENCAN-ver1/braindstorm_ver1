import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import { renderApp, resetGovernor } from '../test/testUtils'

beforeEach(() => resetGovernor())

describe('governed flow integration', () => {
  it('completes the full flow from intake to final handoff via the skip path', async () => {
    const user = userEvent.setup()
    renderApp(['/'])

    // Intake
    expect(await screen.findByRole('heading', { name: /start a brainstorm/i })).toBeInTheDocument()
    await user.type(screen.getByLabelText(/what is your idea/i), 'A guided brainstorm host')
    await user.click(screen.getByLabelText('I just have an idea'))
    await user.click(screen.getByRole('button', { name: /continue/i }))

    // Six frames
    await user.type(screen.getByLabelText('Target user'), 'Product teams')
    await user.type(screen.getByLabelText('Core task'), 'Shape ideas')
    await user.click(screen.getByRole('button', { name: /continue/i }))

    await user.type(screen.getByLabelText('Desired change'), 'Decide with evidence')
    await user.click(screen.getByRole('button', { name: /continue/i }))

    await user.click(screen.getByRole('button', { name: /add hard constraints/i }))
    await user.type(screen.getByLabelText('Hard constraints item 1'), 'Local only')
    await user.click(screen.getByRole('button', { name: /continue/i }))

    await user.click(screen.getByRole('button', { name: /add success metrics/i }))
    await user.type(screen.getByLabelText('Success metrics item 1'), 'A clear handoff')
    await user.click(screen.getByRole('button', { name: /continue/i }))

    await user.click(screen.getByRole('button', { name: /add abandonment criteria/i }))
    await user.type(screen.getByLabelText('Abandonment criteria item 1'), 'No viable path')
    await user.click(screen.getByRole('button', { name: /continue/i }))

    await user.click(screen.getByRole('button', { name: /add non-goals/i }))
    await user.type(screen.getByLabelText('Non-goals item 1'), 'Deployment')
    await user.type(screen.getByLabelText('Validation horizon'), 'One session')

    // Complete the wizard → create session → run → EXPLORE
    await user.click(screen.getByRole('button', { name: /complete/i }))
    await user.click(
      await screen.findByRole('button', { name: /configure external capabilities/i }),
    )

    // Skip capabilities → human gate
    await user.click(screen.getByRole('button', { name: /skip capabilities/i }))
    await user.click(await screen.findByRole('button', { name: /confirm/i }))

    // COMMIT → final handoff
    expect(await screen.findByRole('heading', { name: /final handoff/i })).toBeInTheDocument()
    expect(screen.getByText(/no real governor evidence/i)).toBeInTheDocument()
  })
})
