import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'
import { SessionProvider } from '../../state/SessionContext'
import { IdeaIntakePage } from './IdeaIntakePage'

const renderIntake = () =>
  render(
    <MemoryRouter initialEntries={['/intake']}>
      <SessionProvider>
        <Routes>
          <Route path="/intake" element={<IdeaIntakePage />} />
          <Route path="/frames/who-and-job" element={<div>first-frame</div>} />
        </Routes>
      </SessionProvider>
    </MemoryRouter>,
  )

beforeEach(() => sessionStorage.clear())

describe('IdeaIntakePage', () => {
  it('renders exactly the four idea stage choices with no fifth mode', () => {
    renderIntake()
    const choices = [
      'I just have an idea',
      'I want to explore possibilities',
      'I already have a solution',
      'I need to make a decision',
    ]
    for (const choice of choices) {
      expect(screen.getByLabelText(choice)).toBeInTheDocument()
    }
    expect(screen.getAllByRole('radio')).toHaveLength(4)
  })

  it('blocks continuing until both an idea and a stage are provided', async () => {
    const user = userEvent.setup()
    renderIntake()

    await user.click(screen.getByRole('button', { name: /continue/i }))
    expect(screen.getByText(/describe your idea before continuing/i)).toBeInTheDocument()
    expect(screen.getByText(/choose how you want to proceed/i)).toBeInTheDocument()
    expect(screen.queryByText('first-frame')).not.toBeInTheDocument()

    await user.type(screen.getByLabelText(/what is your idea/i), 'A guided brainstorm host')
    await user.click(screen.getByLabelText('I just have an idea'))
    await user.click(screen.getByRole('button', { name: /continue/i }))

    expect(await screen.findByText('first-frame')).toBeInTheDocument()
  })
})
