# Brainstorm Web Frontend Contract

Status: frozen for P7 implementation. Authority: `artifacts/brainstorm-web-host-v2.p6-handoff.json` in the primary workspace (SHA-256 `f559307a6dde234be436cfaa2aa59097f1626e28b7fd6fd2a1971724ef858421`).

## State ownership

- `BrainstormSession` is the typed API representation returned by the host boundary.
- `FrontendSessionState` is a recoverable UI projection. It may persist only non-secret draft and navigation data.
- The backend Governor and Living Brief remain canonical workflow truth.
- Provider API keys are `EphemeralProviderSecret`; they remain in capability-screen component state and are never serialised.

## Required types

```ts
type GovernorMode = 'Shape' | 'Spark' | 'Stress' | 'Decide'
type KnowledgeStatus = 'UNKNOWN' | 'ASSUMPTION' | 'KNOWN' | 'CONFLICT'
type GovernorStatus = 'NEEDS_INPUT' | 'RESEARCH_REQUIRED' | 'EXPLORE' | 'ITERATE' | 'PARK' | 'COMMIT'
type StageStatus = 'pending' | 'running' | 'complete' | 'needs_input' | 'blocked' | 'skipped' | 'failed'

interface FrameValue<T> { value: T; status: KnowledgeStatus; source: 'user' | 'ai' }

interface FrameSchema {
  target_user: FrameValue<string>
  core_task: FrameValue<string>
  desired_change: FrameValue<string>
  hard_constraints: FrameValue<string[]>
  success_metrics: FrameValue<string[]>
  abandonment_criteria: FrameValue<string[]>
  non_goals: FrameValue<string[]>
  validation_horizon: FrameValue<string>
}
```

AI-originated suggestions start as `ASSUMPTION`. Only an explicit user confirmation may change them to `KNOWN`.

## Idea mapping

| UI choice | Governor mode |
|---|---|
| I just have an idea | Shape |
| I want to explore possibilities | Spark |
| I already have a solution | Stress |
| I need to make a decision | Decide |

No fifth mode is allowed.

## Six-frame mapping

| Wizard frame | Canonical fields |
|---|---|
| Who & Job | `target_user`, `core_task` |
| Desired Change | `desired_change` |
| Constraints | `hard_constraints` |
| Success | `success_metrics` |
| Failure Boundary | `abandonment_criteria` |
| Scope & Validation | `non_goals`, `validation_horizon` |

Required continuation is blocked when a required value is blank or `UNKNOWN`. Validation names the exact field and the corrective action.

## API boundary

```ts
interface BrainstormApi {
  createSession(request: CreateBrainstormRequest): Promise<BrainstormSession>
  saveFrames(sessionId: string, revision: number, frames: FrameSchema): Promise<BrainstormSession>
  startRun(sessionId: string, revision: number): Promise<BrainstormSession>
  resumeRun(sessionId: string, revision: number, input: MissingInputSubmission): Promise<BrainstormSession>
  configureCapabilities(sessionId: string, revision: number, request: CapabilityRequest): Promise<BrainstormSession>
  submitHumanGate(sessionId: string, revision: number, decision: HumanGateDecision): Promise<BrainstormSession>
  getHandoff(sessionId: string): Promise<HandoffContract | null>
}
```

All calls return typed errors for timeout, network failure, `401`, `403`, `409` revision conflict, provider failure and validation failure. React components do not call `fetch` directly.

## Development mock

The mock adapter is selected only by Vite development/test configuration, displays a persistent “Development simulation” label, and never claims to call the real Governor. It preserves non-secret `FrontendSessionState` in versioned `sessionStorage` for refresh recovery. It must never serialise provider API keys or authorization secrets.

## Capability authorization

Research, Council and Evaluator share one gate. Before a provider operation the user sees what is shared, who receives it and why. Credentials alone do not authorize an operation. Council requires two distinct provider names and valid URL/model/key fields. Skip is a first-class result.

## Handoff gate

The formal handoff renders only when `governorStatus === 'COMMIT'`. Every other legal state renders a status-specific continuation or stop view and must not use “Final”, “Approved” or “Ready for implementation”.
