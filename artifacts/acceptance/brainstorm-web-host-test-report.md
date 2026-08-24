# Brainstorm Web Host — Test & Build Report

Generated: 2026-08-24 (Asia/Shanghai)

Revision: `329b2b71a27378b778175d2583c33f62b685e19e` plus the T5 working-tree changes recorded by this report

P7 result: `COMMIT` candidate; final status is determined by `p7-manifest.json` and `validate_p7.py`.

## Web frontend (`web/`)

| Check | Command | Result |
|---|---|---|
| Typecheck | `npm run typecheck` | PASS, exit 0 |
| Lint | `npm run lint` | PASS, exit 0; 0 errors, 1 existing `react-refresh/only-export-components` warning in `SessionContext.tsx` |
| Unit/integration | `npm test` | PASS, 11 files / 54 tests after the final keyboard test was added |
| Production build | `npm run build` | PASS, 64 modules; CSS 4.32 kB (1.42 kB gzip), JS 260.06 kB (82.26 kB gzip) |

The suite covers exact stage mappings; six-frame canonical fields and knowledge status; allowlisted non-secret persistence; mock state transitions and revision conflicts; StrictMode duplicate-start idempotency; `NEEDS_INPUT` same-lineage resume; Council validation/authorization/failure; COMMIT-only handoff; full skip flow; refresh recovery; labels, errors, focus, skip link, and keyboard Tab/Arrow navigation.

## P0–P6 regression (repository root)

| Check | Command | Result |
|---|---|---|
| Repository tests | `python -m unittest discover -s tests -q` | PASS, 108 tests in 129.449 s |
| Governor skill tests | `python -m unittest discover -s .agents/skills/brainstorm-governor/tests -q` | PASS, 108 tests |
| Regression gate | `python ci\regression_gate.py check` | PASS, `ALLOW`, 0 changed dimensions, 0 failing cases |
| Full Version report | `python acceptance\full_version.py validate-report` | PASS, `FULL_VERSION`, AC-01 through AC-08 PASS |

The pinned P6 handoff digest remains `f559307a6dde234be436cfaa2aa59097f1626e28b7fd6fd2a1971724ef858421`.
