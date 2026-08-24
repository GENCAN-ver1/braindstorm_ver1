# Brainstorm Web Host DeepSeek Test Report

Status: PASS — local implementation gates and the real DeepSeek P1 → independent P6 → COMMIT vertical slice pass.

## Passed on 2026-08-24

- Python full suite: 123 tests passed in 43.816s with the test temp root pinned under `var/test-temp`.
- DeepSeek adapter and web-host service targeted regression: 11 tests passed, including fixed endpoint/model, disabled thinking, 8192-token cap, call-time secret resolution, safe failure diagnostics, usage retention on invalid output, schema validation and idempotency.
- Web-host service: 6 tests passed (NEEDS_INPUT without Provider call, schema validation, durable state, sequential/concurrent revision idempotency, bounded evaluator before COMMIT).
- Same-origin server: 4 tests passed (Origin/Host boundary, JSON/body limits, security headers, stack/path redaction).
- Frontend: 58 tests across 12 files passed; typecheck passed; lint had 0 errors and the pre-existing Fast Refresh warning; production build passed with 65 modules.
- Production bundle selection: `/api/v1` and the governed DeepSeek label are present; mock storage key and “Development simulation” are absent.
- Local production host: `/api/v1/health` returned 200 and `/` served the built SPA with CSP.
- P0–P6 regression: 12/12 scenarios valid.
- P7 validator: valid, zero errors/warnings, gate `DEVELOPING`.

## Real Provider result on 2026-08-24

- The newly authorized smoke completed with status `COMMIT` and a durable handoff for session `session-d106427ec0f24b75a592f03ca5aba64a`.
- P1 generation used request `158f06bf-7c06-4fbc-a4a2-cdec1a31cf8e`: 1162 prompt, 1430 completion and 2592 total tokens; measured latency 23615.361 ms.
- Independent P6 evaluation used request `7735d8e6-8076-4bf0-83b9-4078ee9799bf`: 1218 prompt, 1 completion and 1219 total tokens; measured latency 1325.447 ms.
- Exactly two newly authorized calls were made. P6 was invoked only after P1 passed the strict local Governor contract.
- The real result includes three mechanism-distinct candidates, challenges, assessments, a recommendation, Provider receipt, bounded evaluator approval and COMMIT-only handoff.
- No raw Provider response, prompt, credential, stack or internal path was emitted or persisted.

Two earlier authorized P1 failures remain recorded as historical evidence. Their request IDs and token counts are unavailable because the pre-fix service persisted usage only after contract acceptance; historical usage was not fabricated. The fixed service now records usage immediately after generation, including later contract failures.

## Environment observation

Two earlier full-suite attempts hit transient Windows local socket/system-Temp file-lock errors. The affected server, resume-matrix and clean-room modules all passed when rerun individually, and the final 123-test suite passed after pinning its temporary root inside the project. No P0–P6 runtime change was made for these environment-only failures.
