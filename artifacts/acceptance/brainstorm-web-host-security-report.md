# Brainstorm Web Host — Security Review (code inspection)

Status: reviewed by code inspection; no real-browser security tooling was available.

## Controls verified

- **Secret management (A7)**: provider API keys are typed `EphemeralProviderSecret` and held only in `CouncilForm` component state. The development mock strips `providers` (which carry `apiKey`) from every persisted snapshot; the allowlisted frontend-session projection contains no key field. Verified by `ExternalCapabilityGate.test.tsx` ("never persists provider API keys") and `sessionPersistence.test.ts` ("never serialises provider keys").
- **Input validation**: session restore validates version, value types, size bounds, and an allowlisted route set; frame continuation blocks blank/`UNKNOWN` values; provider fields require non-blank name/baseUrl/model/key.
- **Output encoding**: all dynamic text is rendered through React's default escaping; no `dangerouslySetInnerHTML`; the handoff `problem_frame` renders inside `<pre>` (escaped).
- **Allowlisted persistence**: versioned, allowlisted, non-secret `sessionStorage` projection with safe degradation when storage is unavailable.
- **Ephemeral credentials + explicit authorization**: credentials exist only in component state; an explicit authorization checkbox is required before any provider call.
- **Production mock exclusion**: the development mock is the only adapter and is persistently labelled "Development simulation"; no real Governor/Provider is claimed (a P7 non-goal).
- **Dependency review**: `npm ci` reported 0 vulnerabilities (270 packages audited).

## Residual risks / notes

- The mock adapter is not gated behind `import.meta.env.DEV`; it is always the adapter. Acceptable for this MVP because the app never claims real integration and always shows the "Development simulation" label, but a production build requires a real `BrainstormApi` implementation (explicitly out of scope).
- No real-browser security scan was performed; A11's security-review portion is supported by this code-inspection review only.
