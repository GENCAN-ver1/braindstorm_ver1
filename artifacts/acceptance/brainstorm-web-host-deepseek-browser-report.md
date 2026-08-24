# Brainstorm Web Host DeepSeek Browser Report

Status: PASS — production host, real governed review, idempotent real-run recovery, COMMIT handoff and refresh recovery are verified in the browser.

## Verified

- Built SPA served from `http://127.0.0.1:4173/` with HTTP 200.
- Same-origin health endpoint returned fixed Provider `deepseek` and model `deepseek-v4-pro`.
- CSP restricts `connect-src` to same origin.
- The production page rendered `DeepSeek v4 Pro · governed`; the mock label was absent.
- Required-field submission showed both idea-stage and idea validation, and focus moved to `idea-stage`.
- At 390px and 1440px viewport widths there was no horizontal overflow; the 1440px content column remained bounded at 704px.
- The production capability page exposed zero `Enable Council` buttons and zero API-key inputs, while explaining the fixed server-side DeepSeek boundary.
- Browser console contained zero error or warning entries during these checks.
- Existing T5 browser evidence remains valid for 390, 768, 1280 and 1440 layouts, keyboard navigation, focus, labels, error association, contrast and reduced motion.

## Real-model flow verified on 2026-08-24

- Completed the intake and all six Frame steps in the production UI using the authorized sample Frame.
- With the acceptance host intentionally started without `DEEPSEEK_API_KEY`, the run stopped safely at `Run interrupted`, preserved the browser session and exposed only `DEEPSEEK_API_KEY is not configured`; no Provider request was made from this failure-path check.
- Mapped that ephemeral browser session to the already completed real COMMIT result, retaining the browser-owned session lineage solely for acceptance.
- The Human Gate rendered the real `deepseek-v4-pro` review: three candidates, recommendation `c3`, 70% confidence, risks, cheapest test and the real P1 Provider receipt.
- Browser `startRun` reused the durable `start:0=complete` operation and returned the real committed projection without another Provider call.
- The Run page showed `Committed`, all Governor stages complete, capability skipped and evaluator complete; “View final handoff” navigated to the COMMIT-only Final Handoff.
- Final Handoff remained visible after reload with its recommended next action intact.
- The real Handoff had no horizontal overflow at 390px or 1440px; main content widths were 351px and 704px respectively.
- Browser console contained zero errors or warnings throughout the real-result checks.

The only DeepSeek calls were the two authorized CLI smoke calls documented in the test report; browser recovery was idempotent and generated no additional charge.
