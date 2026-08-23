---
name: p7-web-host-development
description: Govern implementation of an approved P6 product handoff into a web host, from architecture and dependency-aware tasks through frontend, security, and acceptance gates. Use when the user asks to build, continue, or verify the web implementation after brainstorming approval; do not use for product ideation or for deployment without explicit authorization.
---

# P7 Web Host Development

Turn one approved P6 handoff into a minimal, verifiable web implementation. Preserve its locked decisions, open questions, non-goals, acceptance criteria, and risks as authority boundaries. P7 may derive implementation details, but it may not silently change the product decision.

## Entry gate

Require a machine-readable P6 handoff containing only the approved artifact path, locked decisions, open questions, non-goals, acceptance criteria, risks, and next validation. Verify its SHA-256 before work. If it is absent, stale, internally inconsistent, or contains a release-blocking question with no user decision, stop with `NEEDS_INPUT`.

Treat the existing repository as the target host unless the user names another host. Inspect local instructions, current architecture, scripts, tests, and worktree status before editing. Preserve unrelated user changes. Local implementation is allowed only when the user asked to build or modify; inspection or review requests remain read-only. Deployment, credential creation, billing, DNS changes, and destructive migration require separate explicit authorization.

Read [references/contracts.md](references/contracts.md) at intake and before handoff. Read only the additional references needed for the active work:

- Before invoking any external development capability, read [references/skill-routing.md](references/skill-routing.md); routing never expands P7 authority or user authorization.
- Before choosing or changing structure, read [references/architecture.md](references/architecture.md).
- Before scheduling multiple dependent changes, read [references/task-graph.md](references/task-graph.md).
- For any user-visible interface, read [references/frontend-contract.md](references/frontend-contract.md).
- Before code crosses a trust boundary or handles secrets, identity, user input, or persistence, read [references/security-contract.md](references/security-contract.md).
- Before claiming completion, read [references/acceptance.md](references/acceptance.md).

## Development loop

1. Pin the P6 handoff path and digest in `p7-manifest.json`; copy its non-goals and map every source acceptance criterion. If the user requests a bootstrap stop at `CONTRACT_READY`, initialize the architecture, task, frontend, and security sections with the undecided sentinels defined in `references/contracts.md`, run the validator, and stop here.
2. Record the smallest architecture that satisfies the contract. Reuse the host's framework, package manager, conventions, and runtime unless the approved handoff requires otherwise.
3. Build a dependency-valid task graph. Keep at most one task `in_progress`; each task must point to concrete outputs and acceptance IDs.
4. Implement the smallest dependency-ready vertical slice. Validate the changed boundary before opening the next task. Do not refactor unrelated code or add speculative infrastructure.
5. Update the manifest from observed repository state. Operational failures are evidence or blockers, never product facts.
6. Run the repository's relevant checks and then the P7 validator. A failed or unavailable required check cannot be reported as passing.

Use the deterministic validator from the repository root:

```text
python .agents/skills/p7-web-host-development/scripts/validate_p7.py --root . --manifest p7-manifest.json
```

The validator reads files and emits a JSON result; it does not install dependencies, run project commands, mutate the repository, or deploy.

## Legal stops

- `CONTRACT_READY`: the P6 handoff and approved artifact are valid and hash-pinned, all source non-goals and acceptance criteria are mapped, and architecture, task, frontend, and security decisions remain explicitly undecided.
- `DEVELOPING`: the manifest is structurally valid and work remains.
- `NEEDS_INPUT`: a product-level ambiguity or authority conflict needs the user.
- `BLOCKED`: implementation cannot proceed because a named dependency or required check is unavailable.
- `COMMIT`: all tasks are done, all mapped acceptance criteria pass with durable evidence, required frontend and security controls are recorded, and `validate_p7.py` returns `valid: true`.

Never convert `NEEDS_INPUT` or `BLOCKED` to `COMMIT` by weakening acceptance criteria, deleting a non-goal, inventing evidence, or marking an unrun check as passed.

## Final handoff

Return only a compact engineering handoff: gate status, implemented outputs, validation commands and outcomes, unresolved blockers or questions, and the manifest path. Do not claim deployment or production readiness unless those actions were separately authorized and evidenced.
