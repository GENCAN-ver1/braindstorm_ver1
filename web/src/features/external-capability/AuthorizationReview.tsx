interface ProviderDraft {
  name: string
  baseUrl: string
  model: string
  apiKey: string
}

export function AuthorizationReview({
  providers,
  authorized,
  onAuthorize,
}: {
  providers: ProviderDraft[]
  authorized: boolean
  onAuthorize: (authorized: boolean) => void
}) {
  const recipientNames = providers.map((provider) => provider.name.trim()).filter(Boolean)

  return (
    <section aria-labelledby="authorization-heading">
      <h3 id="authorization-heading">Authorization review</h3>
      <p>Enabling the Council shares the following with each provider you configure:</p>
      <ul>
        <li>Provider name, base URL, and model identifier</li>
        <li>Your API key (sent only at call time; never persisted)</li>
      </ul>
      {recipientNames.length > 0 && <p>Recipients: {recipientNames.join(', ')}</p>}
      <p>Each provider receives its own request and cannot see other providers&apos; output.</p>
      <label>
        <input
          type="checkbox"
          checked={authorized}
          onChange={(event) => onAuthorize(event.target.checked)}
        />
        I authorize sending these fields to the configured providers.
      </label>
    </section>
  )
}
