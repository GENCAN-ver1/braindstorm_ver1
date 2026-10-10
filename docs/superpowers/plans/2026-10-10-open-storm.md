# Open Storm implementation plan

**Goal:** Build the approved low-input brainstorming design with configurable DS, Kimi, GLM, Qwen APIs and local subscription Codex.
**Architecture:** Add an exploration graph and a separate CLI inside the current repository. Keep the existing decision runtime available for subsequent validated decisions. Roles and providers are independent. No credentials or current flagship model IDs are assumed.
**Tech stack:** Python standard library, unittest, existing Codex CLI.
**Spec:** User-approved role × creative operation design in this conversation, 2026-10-10.

## Constraints and review focus
- Plain topic starts exploration without a complete Frame.
- Independent rounds exclude peer output; later rounds explicitly choose parents.
- Unknowns remain hypotheses; no early scoring or forced winner.
- Provider failures remain failures, never idea nodes; keys and raw error bodies are not persisted.
- Local OpenAI requires ChatGPT login and never silently falls back to API billing.
- Graph saves are atomic; existing state files are not overwritten by init.
- Live calls are explicit and bounded; no automatic retries after ambiguous failures.

## Tasks
- [x] Write behavioral tests and observe missing runtime fail.
- [x] Implement persistent graph, role prompts, question branches, and explicit convergence.
- [x] Implement provider adapter and disabled configuration entries for all five providers.
- [x] Add CLI init, prepare, import, round, answer, converge, export, status.
- [x] Add Open Storm skill and usage guide; route concept exploration into the new entry.
- [x] Run focused and existing regression tests; report live integration boundaries.

Validation details: `docs/OPEN_STORM_VERIFICATION.md`. Full release gate remains BLOCK pending approved live regression. No baseline was updated.

Execution: inline, directly authorized by the user. No commits or pushes requested.
