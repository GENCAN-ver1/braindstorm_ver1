# Brainstorm Web Host DeepSeek Security Report

Status: PASS — static/local controls, live failure redaction and the successful P1/P6/COMMIT path are verified.

## Implemented controls

- Outbound generation is fixed to `https://api.deepseek.com/chat/completions` and `deepseek-v4-pro`; browser input cannot set endpoint, model or credential.
- `DEEPSEEK_API_KEY` is resolved only at the narrow server call boundary and is absent from returned results and errors.
- Model input is marked DATA_ONLY; output must be a JSON object, cannot contain tool calls, must finish normally, and must pass the existing strict P1 schema/state machine before canonical persistence.
- Provider response is limited to 1 MiB and 60 seconds; request bodies are limited to 64 KiB; session operations are revision-idempotent.
- Provider usage is copied only from the response. Missing token fields remain `null`; cost is not estimated.
- Session files contain normalized governed output and usage receipts, never raw Provider responses, authorization headers or credentials.
- Host binds only to localhost, enforces Host/Origin and JSON content type, applies a bounded request rate, suppresses request logging and returns redacted errors.
- CSP, `nosniff`, frame denial, referrer policy, permissions policy and cross-origin opener policy are emitted on API/static responses.
- Production Vite resolution selects only the real HTTP adapter. The production bundle contains neither the mock storage key nor the simulation label.
- Real mode hides configurable Provider URLs/browser API keys and explicitly disables multi-provider Council.

## Live failure-path verification

- Two authorized P1 calls failed safely without exposing raw Provider responses, credentials, stack traces or internal paths.
- Persisted real-smoke session files contain none of `Authorization`, `Bearer `, `DEEPSEEK_API_KEY`, `api_key` or `raw_response`.
- A discovered audit gap—usage was written only after contract acceptance—has been fixed and regression-tested. Usage from the two historical failed calls could not be recovered and was not estimated.

## Remaining boundary

The successful P1 and independent P6 calls persisted only normalized governed output and Provider usage receipts. The production browser rendered the resulting review and COMMIT handoff, recovered it after refresh, and emitted zero console errors or warnings. No credential, authorization header, raw Provider response or prompt appeared in the API projection, browser UI, persisted session, acceptance evidence or client bundle.
