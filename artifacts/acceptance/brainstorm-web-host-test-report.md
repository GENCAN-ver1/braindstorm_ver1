# Brainstorm Web Host — Test & Build Report

Generated: 2026-08-23 (Asia/Shanghai)
P7 gate: `DEVELOPING`

## Web frontend (run from `web/` with npm)

| Check | Command | Result |
|---|---|---|
| Typecheck | `npm run typecheck` | exit 0 |
| Lint | `npm run lint` | exit 0 (1 warning: react-refresh for `SessionContext` `useSession` hook — idiomatic React context pattern) |
| Unit/integration tests | `npx vitest --run` | 11 files / 51 tests passed |
| Production build | `npm run build` | exit 0 (64 modules; CSS 3.96 kB gzip 1.31 kB; JS 258.83 kB gzip 81.99 kB) |
| P7 validator | `python .agents/skills/p7-web-host-development/scripts/validate_p7.py --root . --manifest p7-manifest.json` | `valid:true`, 0 errors, 0 warnings |

## Behavior coverage by scenario

- **Idea intake**: four idea-stage choices map exactly to Shape/Spark/Stress/Decide; blocking validation until an idea and a stage are provided (`IdeaIntakePage.test.tsx`, `mappings.test.ts`).
- **Six-frame wizard**: canonical field mapping, `UNKNOWN`/blank continuation blocking, next/back navigation, list-field editing (`FrameWizardPage.test.tsx`).
- **Session persistence**: versioned allowlisted projection, provider-secret exclusion, malformed/out-of-bounds rejection, storage-failure results (`sessionPersistence.test.ts`).
- **Development mock state machine**: complete run → `EXPLORE`; incomplete → `NEEDS_INPUT` then same-lineage resume; standard skip; Council distinct-name validation; provider failure; COMMIT-only handoff; revision-conflict rejection (`developmentMock.test.ts`).
- **Run / NEEDS_INPUT**: run page expresses stages + legal status; missing-input panel resumes (`RunPage.test.tsx`).
- **Capability gate**: skip as first-class result; Council enable with two distinct providers + explicit authorization; provider API key never reaches storage (`ExternalCapabilityGate.test.tsx`).
- **Human gate / handoff**: COMMIT-only final handoff (`HandoffPage.test.tsx`).
- **End-to-end**: intake → six frames → run → skip → human gate → final handoff; refresh recovery (`governedFlow.integration.test.tsx`, `intakeFrames.integration.test.tsx`).
- **Accessibility semantics**: single level-one heading, labelled controls, error association via `aria-describedby` + `role="alert"` (`accessibility.test.tsx`).

## P0–P6 regression (primary workspace)

| Check | Command | Result |
|---|---|---|
| Repository tests | `python -m unittest discover -s tests -q` | 108 tests OK |
| Skill tests | `python -m unittest discover -s .agents/skills/brainstorm-governor/tests -q` | 108 tests OK |
| Regression gate | `python ci\regression_gate.py check` | `ALLOW` |
| Full Version | `python acceptance\full_version.py validate-report` | `PASS` |
