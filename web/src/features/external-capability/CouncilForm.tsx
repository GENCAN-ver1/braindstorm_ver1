import { useState } from 'react'
import type { CapabilityProvider, EphemeralProviderSecret } from '../../api/BrainstormApi'
import { AuthorizationReview } from './AuthorizationReview'

interface ProviderDraft {
  name: string
  baseUrl: string
  model: string
  apiKey: string
}

const emptyProvider = (): ProviderDraft => ({ name: '', baseUrl: '', model: '', apiKey: '' })

export function CouncilForm({
  onConfigure,
}: {
  onConfigure: (providers: CapabilityProvider[]) => void
}) {
  const [providers, setProviders] = useState<ProviderDraft[]>([emptyProvider(), emptyProvider()])
  const [authorized, setAuthorized] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const updateProvider = (index: number, patch: Partial<ProviderDraft>) => {
    setProviders((prev) => prev.map((provider, i) => (i === index ? { ...provider, ...patch } : provider)))
  }

  const addProvider = () => setProviders((prev) => [...prev, emptyProvider()])

  const removeProvider = (index: number) =>
    setProviders((prev) => prev.filter((_, i) => i !== index))

  const trimmed = providers.map((provider) => ({
    ...provider,
    name: provider.name.trim(),
    baseUrl: provider.baseUrl.trim(),
    model: provider.model.trim(),
  }))

  const distinctNames = new Set(trimmed.map((provider) => provider.name)).size === trimmed.length
  const allFieldsFilled = trimmed.every(
    (provider) => provider.name && provider.baseUrl && provider.model && provider.apiKey.trim(),
  )
  const valid = providers.length >= 2 && allFieldsFilled && distinctNames && authorized

  const handleSubmit = () => {
    if (providers.length < 2) {
      setError('A Council requires at least two providers.')
      return
    }
    if (!allFieldsFilled) {
      setError('Every provider needs a name, base URL, model, and API key.')
      return
    }
    if (!distinctNames) {
      setError('Council providers must have distinct names.')
      return
    }
    if (!authorized) {
      setError('Authorize the provider calls before enabling the Council.')
      return
    }
    setError(null)
    const branded: CapabilityProvider[] = trimmed.map((provider) => ({
      name: provider.name,
      baseUrl: provider.baseUrl,
      model: provider.model,
      apiKey: provider.apiKey as EphemeralProviderSecret,
    }))
    onConfigure(branded)
  }

  return (
    <section aria-labelledby="council-heading">
      <h2 id="council-heading">Council providers</h2>
      {providers.map((provider, index) => (
        <fieldset key={index}>
          <legend>Provider {index + 1}</legend>
          <div>
            <label htmlFor={`provider-${index}-name`}>Name</label>
            <input
              id={`provider-${index}-name`}
              name={`provider-${index}-name`}
              autoComplete="off"
              spellCheck={false}
              value={provider.name}
              onChange={(event) => updateProvider(index, { name: event.target.value })}
            />
          </div>
          <div>
            <label htmlFor={`provider-${index}-baseUrl`}>Base URL</label>
            <input
              id={`provider-${index}-baseUrl`}
              name={`provider-${index}-baseUrl`}
              type="url"
              inputMode="url"
              autoComplete="off"
              spellCheck={false}
              value={provider.baseUrl}
              onChange={(event) => updateProvider(index, { baseUrl: event.target.value })}
            />
          </div>
          <div>
            <label htmlFor={`provider-${index}-model`}>Model</label>
            <input
              id={`provider-${index}-model`}
              name={`provider-${index}-model`}
              autoComplete="off"
              spellCheck={false}
              value={provider.model}
              onChange={(event) => updateProvider(index, { model: event.target.value })}
            />
          </div>
          <div>
            <label htmlFor={`provider-${index}-apiKey`}>API key</label>
            <input
              id={`provider-${index}-apiKey`}
              name={`provider-${index}-apiKey`}
              type="password"
              autoComplete="off"
              spellCheck={false}
              value={provider.apiKey}
              onChange={(event) => updateProvider(index, { apiKey: event.target.value })}
            />
          </div>
          {providers.length > 2 && (
            <button type="button" onClick={() => removeProvider(index)}>
              Remove provider {index + 1}
            </button>
          )}
        </fieldset>
      ))}
      <button type="button" onClick={addProvider}>
        Add provider
      </button>

      <AuthorizationReview
        providers={providers}
        authorized={authorized}
        onAuthorize={setAuthorized}
      />

      {error && <p role="alert">{error}</p>}

      <button type="button" onClick={handleSubmit} disabled={!valid}>
        Confirm Council
      </button>
    </section>
  )
}
