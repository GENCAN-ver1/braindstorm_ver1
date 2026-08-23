import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'
import { App } from './App'

const renderApp = (initialEntries = ['/']) =>
  render(
    <MemoryRouter initialEntries={initialEntries}>
      <App />
    </MemoryRouter>,
  )

beforeEach(() => sessionStorage.clear())

describe('intake to frames integration', () => {
  it('completes idea intake and the six-frame wizard end to end', async () => {
    const user = userEvent.setup()
    renderApp()

    expect(await screen.findByRole('heading', { name: /start a brainstorm/i })).toBeInTheDocument()

    await user.type(screen.getByLabelText(/what is your idea/i), 'A guided brainstorm host')
    await user.click(screen.getByLabelText('I just have an idea'))
    await user.click(screen.getByRole('button', { name: /continue/i }))

    await user.type(screen.getByLabelText('Target user'), 'Product teams')
    await user.type(screen.getByLabelText('Core task'), 'Shape ideas')
    await user.click(screen.getByRole('button', { name: /continue/i }))

    await user.type(screen.getByLabelText('Desired change'), 'Reach an evidence-backed decision')
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
    await user.type(screen.getByLabelText('Validation horizon'), 'One local session')
    await user.click(screen.getByRole('button', { name: /complete/i }))

    expect(
      await screen.findByRole('heading', { name: /frame wizard complete/i }),
    ).toBeInTheDocument()
  })

  it('recovers the session after a refresh', async () => {
    const user = userEvent.setup()
    const { unmount } = renderApp()

    await user.type(screen.getByLabelText(/what is your idea/i), 'Refresh me')
    await user.click(screen.getByLabelText('I just have an idea'))
    await user.click(screen.getByRole('button', { name: /continue/i }))
    await user.type(screen.getByLabelText('Target user'), 'Product teams')
    unmount()

    renderApp(['/frames/who-and-job'])
    expect(screen.getByLabelText('Target user')).toHaveValue('Product teams')

    await user.click(screen.getByRole('button', { name: /back/i }))
    expect(await screen.findByLabelText(/what is your idea/i)).toHaveValue('Refresh me')
    expect(screen.getByLabelText('I just have an idea')).toBeChecked()
  })
})
