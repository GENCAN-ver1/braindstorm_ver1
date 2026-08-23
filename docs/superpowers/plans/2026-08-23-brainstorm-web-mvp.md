# Brainstorm Web MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local React web MVP that completes the governed Brainstorm interaction flow using a typed development mock while preserving P0–P6 authority and ephemeral provider secrets.

**Architecture:** A Vite React application owns only UI projection and routing. Domain contracts and pure mappings are framework-independent, one typed `BrainstormApi` boundary owns all async calls, and a development-only mock simulates legal Governor transitions without presenting them as real results. Versioned session storage contains only non-secret projection data.

**Tech Stack:** React 19, TypeScript, Vite, React Router, Vitest, Testing Library, ESLint, npm.

---

### Task 1: Toolchain and typed contracts

**Files:**
- Create: `web/package.json`, `web/package-lock.json`, `web/vite.config.ts`, `web/tsconfig.json`, `web/tsconfig.app.json`, `web/eslint.config.js`, `web/index.html`
- Create: `web/src/types/contracts.ts`, `web/src/types/mappings.ts`, `web/src/state/sessionPersistence.ts`
- Test: `web/src/types/mappings.test.ts`, `web/src/state/sessionPersistence.test.ts`

- [ ] Write failing tests for the four exact mode mappings, six-frame canonical mapping, UNKNOWN continuation blocking, AI ASSUMPTION preservation and secret-safe persistence.
- [ ] Run `npm test -- --run src/types/mappings.test.ts src/state/sessionPersistence.test.ts` and confirm failures are caused by missing modules.
- [ ] Implement the frozen contract types, pure mappings, field validation and allowlisted session projection serialiser.
- [ ] Re-run the focused tests and `npm run typecheck`; expect exit 0.

### Task 2: App shell, intake and six-frame wizard

**Files:**
- Create: `web/src/main.tsx`, `web/src/app/App.tsx`, `web/src/app/router.tsx`, `web/src/app/AppShell.tsx`
- Create: `web/src/features/intake/IdeaIntakePage.tsx`, `web/src/features/frame/FrameWizardPage.tsx`, `web/src/features/frame/frameDefinitions.ts`
- Create: `web/src/state/SessionContext.tsx`, `web/src/components/StatusBadge.tsx`, `web/src/components/FormError.tsx`
- Test: `web/src/features/intake/IdeaIntakePage.test.tsx`, `web/src/features/frame/FrameWizardPage.test.tsx`, `web/src/app/intakeFrames.integration.test.tsx`

- [ ] Write failing behavior tests for idea selection, plain-language intake, contextual six-step navigation, field-specific errors, back/edit, keyboard actions and refresh recovery.
- [ ] Run the focused tests and confirm expected RED failures.
- [ ] Implement semantic forms and route transitions; use native buttons, labels and field error associations.
- [ ] Re-run focused tests and typecheck; expect exit 0.

### Task 3: Typed API, run progression and governed gates

**Files:**
- Create: `web/src/api/BrainstormApi.ts`, `web/src/api/errors.ts`, `web/src/api/developmentMock.ts`, `web/src/api/client.ts`
- Create: `web/src/features/run/RunPage.tsx`, `web/src/features/run/stages.ts`, `web/src/features/run/NeedsInputPanel.tsx`
- Create: `web/src/features/external-capability/ExternalCapabilityGate.tsx`, `web/src/features/external-capability/CouncilForm.tsx`, `web/src/features/external-capability/AuthorizationReview.tsx`
- Create: `web/src/features/human-gate/HumanGatePage.tsx`, `web/src/features/handoff/HandoffPage.tsx`
- Test: `web/src/api/developmentMock.test.ts`, `web/src/features/run/RunPage.test.tsx`, `web/src/features/external-capability/ExternalCapabilityGate.test.tsx`, `web/src/features/handoff/HandoffPage.test.tsx`, `web/src/app/governedFlow.integration.test.tsx`

- [ ] Write failing tests for legal status mapping, standard skip, NEEDS_INPUT resume lineage, Council provider rules, authorization, provider failure/NOT_COUNCIL, revision conflict and COMMIT-only handoff.
- [ ] Add a persistence spy test proving fake keys never reach storage and clear on capability-screen exit.
- [ ] Run the focused tests and confirm RED failures.
- [ ] Implement the typed mock state machine and pages with no component-level `fetch`.
- [ ] Re-run focused tests, full unit/integration suite and typecheck; expect exit 0.

### Task 4: Visual system, responsive behavior and accessibility

**Files:**
- Create: `web/src/styles/tokens.css`, `web/src/styles/global.css`, `web/src/styles/components.css`
- Modify: all user-visible components from Tasks 2–3
- Test: `web/src/app/accessibility.test.tsx`

- [ ] Write failing semantic/accessibility tests for headings, labels, error association, live status, button state and focus placement.
- [ ] Run the focused test and confirm RED failures.
- [ ] Implement the calm high-density visual system, visible focus, reduced-motion rules and responsive layouts for 390/768/1280/1440.
- [ ] Re-run tests, lint, typecheck and production build; expect exit 0.

### Task 5: Browser scenarios, reviews and durable evidence

**Files:**
- Create: `web/e2e/brainstorm-flow.spec.ts`
- Create: `artifacts/acceptance/p7-web-tests.txt`, `artifacts/acceptance/p7-web-e2e.txt`, `artifacts/acceptance/p7-web-reviews.md`
- Modify: `p7-manifest.json` in the primary workspace after evidence is copied back

- [ ] Start the real Vite app and execute browser scenarios A–E against it with fake credentials only.
- [ ] Verify 390/768/1280/1440 viewports, keyboard flow, focus and no horizontal overflow.
- [ ] Run React performance, current Web Interface Guidelines and security reviews; fix every CRITICAL/HIGH and every P7 violation.
- [ ] Run fresh `typecheck`, `lint`, unit/integration tests, production build, P7 validator, P0–P6 tests, regression gate and FV-07 report validation.
- [ ] Record exact commands, exit codes and outcomes in durable evidence, then set the P7 gate only to the highest evidenced legal status.
