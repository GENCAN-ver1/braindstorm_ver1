# Brainstorm Web Host — Browser E2E / UI Report

Generated: 2026-08-24 (Asia/Shanghai)

Revision: `329b2b71a27378b778175d2583c33f62b685e19e` plus the T5 working-tree changes recorded by this report

Runtime: Codex in-app Chromium browser, `http://127.0.0.1:5173/`, Vite development server

Result: **PASS** for A1, A9, and the real-browser portions of A10/A11.

## Governed-flow scenarios

| Scenario | Observed result |
|---|---|
| Standard skip | Idea intake → all six frames → `EXPLORE` → Skip Council → Human Gate → Confirm → Final Handoff completed. |
| `NEEDS_INPUT` | Human Gate requested missing `core_task`; the run entered `NEEDS_INPUT`, accepted the missing value, and resumed the same session lineage to `EXPLORE`. |
| Council authorization | Two distinct providers with separate name/base URL/model/ephemeral key fields enabled Confirm only after explicit authorization; key controls remained masked. |
| Provider failure | Provider name `failing-provider` produced a visible recoverable failure; correcting it to `provider-a` completed the capability step and reached Human Gate. |
| Refresh recovery | Six completed frame values and the Human Gate route survived reload without exposing credentials. |

No browser console errors or warnings were present after the final runs.

## Defects found and closed during T5

- React StrictMode replayed the run mutation and exposed `Expected revision 1, received 0`. The development mock now treats the duplicate start as one idempotent operation, and the governed-flow test now runs under StrictMode.
- Global `input { width: 100% }` stretched radio/checkbox controls. Native choice controls now use intrinsic width; desktop and 390 px browser checks passed after the fix.
- Added a keyboard-visible skip link, first-invalid-field focus, async `role="status"` announcements, field names/autocomplete metadata, URL input semantics, and persistent visible focus treatment.

## Responsive and accessibility observations

- Viewports checked: 390×844, 768 px, 1280 px, and 1440×900. No horizontal overflow was observed; at 390 px, `scrollWidth = clientWidth = 390` and all controls remained inside the viewport.
- Runtime error association: blank idea produced `role="alert"` text `Describe your idea before continuing.`, linked by `aria-describedby="idea-error"`; focus moved to `textarea#idea`.
- Runtime focus treatment: focused controls showed a 3 px visible focus ring. The skip link is hidden until focused.
- Computed contrast samples: body text 15.91:1, form/button text 17.22:1, warning badge 5.36:1, alert text 6.54:1.
- Reduced-motion media rules disable meaningful animation/transition duration and smooth scrolling.
- Native link/button/radio/input semantics, labels, names, masking, and accessible alert/status roles were present in the browser accessibility snapshot.
- The browser connector did not dispatch its synthetic `press()` calls reliably. Sequential Tab/Arrow keyboard behavior is therefore evidenced by the dedicated `userEvent` acceptance test, while visible focus, focus migration, semantics, and layout were observed in the real browser. No synthetic key result is represented as a browser observation.

## UI / React review

- Reviewed against the current Web Interface Guidelines: no unresolved high-impact accessibility or responsive finding remains in the T5 scope.
- React review found no material render waterfall, list, or bundle issue. Sequential `NEEDS_INPUT` mutations are revision-dependent by design; the only runtime StrictMode defect found was fixed and regression-tested.
