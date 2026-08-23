# Architecture Contract

Use this contract when selecting or changing the target host's structure.

## Decision order

1. Preserve the approved P6 behavior and non-goals.
2. Reuse the existing host runtime, framework, package manager, entrypoints, and conventions.
3. Prefer a vertical slice that can be accepted end to end over speculative shared layers.
4. Introduce a new component only when it owns a distinct responsibility or trust boundary.
5. Record assumptions that affect acceptance; escalate product decisions instead of hiding them in architecture.

## Required architecture record

The P7 manifest records:

- `entrypoints`: repository-relative files or directories that start or expose the implementation.
- `components`: unique component IDs, owned paths, one-sentence responsibilities, and component dependencies.
- `decisions`: consequential implementation choices with rationale and the P6 constraint or host fact that caused them.

Dependencies must reference declared components and form a directed acyclic graph. A component owns its listed path; overlapping ownership needs an explicit decision. Keep browser, server, persistence, and external-provider boundaries visible even when one framework contains all of them.

## Change boundary

Architecture work may derive implementation details such as routing, state placement, and module boundaries. It may not change target users, core behavior, locked decisions, source acceptance criteria, or non-goals. When the existing host conflicts with P6, report the conflict as `NEEDS_INPUT` with the smallest viable choices.

Avoid framework replacement, repository-wide reformatting, new infrastructure, or a new persistence/authentication system unless a source criterion or verified host constraint requires it.
