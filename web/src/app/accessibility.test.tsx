import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import { renderApp, resetGovernor } from '../test/testUtils'

beforeEach(() => resetGovernor())

describe('accessibility', () => {
  it('renders a single level-one heading with labelled controls on the intake page', async () => {
    renderApp(['/intake'])

    expect(await screen.findByRole('heading', { name: /start a brainstorm/i })).toBeInTheDocument()
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1)
    expect(screen.getByLabelText(/what is your idea/i)).toBeInTheDocument()
    expect(screen.getAllByRole('radio')).toHaveLength(4)
  })

  it('associates wizard field errors with their inputs via aria-describedby and role=alert', async () => {
    const user = userEvent.setup()
    renderApp(['/frames/who-and-job'])

    await user.click(screen.getByRole('button', { name: /continue/i }))

    const input = screen.getByLabelText('Target user')
    const describedBy = input.getAttribute('aria-describedby')
    expect(describedBy).toBeTruthy()
    const errorElement = document.getElementById(describedBy as string)
    expect(errorElement).toHaveTextContent(/target user is unknown/i)
    expect(errorElement).toHaveAttribute('role', 'alert')
  })

  it('gives every rendered button an accessible name', () => {
    renderApp(['/intake'])
    const buttons = screen.getAllByRole('button')
    expect(buttons.length).toBeGreaterThan(0)
    for (const button of buttons) {
      expect(button.textContent?.trim().length ?? 0).toBeGreaterThan(0)
    }
  })
})
