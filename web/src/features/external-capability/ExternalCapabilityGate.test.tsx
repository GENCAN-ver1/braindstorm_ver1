import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import { completeFrames, renderApp, resetGovernor, seedSession } from '../../test/testUtils'

beforeEach(() => resetGovernor())

describe('ExternalCapabilityGate', () => {
  it('supports skipping capabilities as a first-class result', async () => {
    const user = userEvent.setup()
    await seedSession(completeFrames())
    renderApp(['/capabilities'])

    await user.click(screen.getByRole('button', { name: /skip capabilities/i }))

    expect(await screen.findByRole('heading', { name: /human gate/i })).toBeInTheDocument()
  })

  it('enables the Council with two distinct providers and explicit authorization', async () => {
    const user = userEvent.setup()
    await seedSession(completeFrames())
    renderApp(['/capabilities'])

    await user.click(screen.getByRole('button', { name: /enable council/i }))

    const names = screen.getAllByLabelText('Name')
    const baseUrls = screen.getAllByLabelText('Base URL')
    const models = screen.getAllByLabelText('Model')
    const apiKeys = screen.getAllByLabelText('API key')

    await user.type(names[0], 'provider-a')
    await user.type(baseUrls[0], 'https://a.example.test')
    await user.type(models[0], 'model-a')
    await user.type(apiKeys[0], 'key-a')

    await user.type(names[1], 'provider-b')
    await user.type(baseUrls[1], 'https://b.example.test')
    await user.type(models[1], 'model-b')
    await user.type(apiKeys[1], 'key-b')

    await user.click(screen.getByRole('checkbox', { name: /i authorize/i }))
    await user.click(screen.getByRole('button', { name: /confirm council/i }))

    expect(await screen.findByRole('heading', { name: /human gate/i })).toBeInTheDocument()
  })

  it('never persists provider API keys', async () => {
    const user = userEvent.setup()
    await seedSession(completeFrames())
    renderApp(['/capabilities'])

    await user.click(screen.getByRole('button', { name: /enable council/i }))
    await user.type(screen.getAllByLabelText('API key')[0], 'super-secret-key-123')

    const allStorage = Object.keys(sessionStorage)
      .map((key) => sessionStorage.getItem(key) ?? '')
      .join(' ')

    expect(allStorage).not.toContain('super-secret-key-123')
  })
})
