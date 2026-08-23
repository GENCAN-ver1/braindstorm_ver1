import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'
import { SessionProvider } from '../../state/SessionContext'
import { FrameWizardPage } from './FrameWizardPage'

const renderFrame = (slug: string) =>
  render(
    <MemoryRouter initialEntries={[`/frames/${slug}`]}>
      <SessionProvider>
        <Routes>
          <Route path="/frames/:frameSlug" element={<FrameWizardPage />} />
        </Routes>
      </SessionProvider>
    </MemoryRouter>,
  )

beforeEach(() => sessionStorage.clear())

describe('FrameWizardPage', () => {
  it('renders the Who & Job frame with its two canonical fields', () => {
    renderFrame('who-and-job')
    expect(screen.getByRole('heading', { name: /who & job/i })).toBeInTheDocument()
    expect(screen.getByLabelText('Target user')).toBeInTheDocument()
    expect(screen.getByLabelText('Core task')).toBeInTheDocument()
  })

  it('blocks continuation with field-specific errors for UNKNOWN required fields', async () => {
    const user = userEvent.setup()
    renderFrame('who-and-job')

    await user.click(screen.getByRole('button', { name: /continue/i }))

    expect(screen.getByText(/target user is unknown/i)).toBeInTheDocument()
    expect(screen.getByText(/core task is unknown/i)).toBeInTheDocument()
  })

  it('advances to the next frame once required fields are provided', async () => {
    const user = userEvent.setup()
    renderFrame('who-and-job')

    await user.type(screen.getByLabelText('Target user'), 'Product teams')
    await user.type(screen.getByLabelText('Core task'), 'Shape ideas')
    await user.click(screen.getByRole('button', { name: /continue/i }))

    expect(await screen.findByRole('heading', { name: /desired change/i })).toBeInTheDocument()
  })

  it('supports back navigation to the previous frame', async () => {
    const user = userEvent.setup()
    renderFrame('desired-change')

    await user.click(screen.getByRole('button', { name: /back/i }))

    expect(await screen.findByRole('heading', { name: /who & job/i })).toBeInTheDocument()
  })

  it('adds and removes list items for list-kind fields', async () => {
    const user = userEvent.setup()
    renderFrame('constraints')

    await user.click(screen.getByRole('button', { name: /add hard constraints/i }))
    await user.type(screen.getByLabelText('Hard constraints item 1'), 'Local only')
    expect(screen.getByLabelText('Hard constraints item 1')).toHaveValue('Local only')

    await user.click(screen.getByRole('button', { name: /add hard constraints/i }))
    await user.type(screen.getByLabelText('Hard constraints item 2'), 'No deployment')

    await user.click(screen.getByRole('button', { name: /remove hard constraints item 1/i }))
    expect(screen.queryByLabelText('Hard constraints item 2')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Hard constraints item 1')).toHaveValue('No deployment')
  })
})
