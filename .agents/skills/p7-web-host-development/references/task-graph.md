# Task Graph Contract

Use a directed acyclic graph when implementation has multiple dependent outputs.

## Node rules

Each task has one observable outcome and records:

- a stable unique `id` and action-oriented `title`;
- `depends_on` IDs that must be `done` first;
- concrete repository-relative `outputs`;
- the `acceptance_ids` it advances;
- one status: `pending`, `in_progress`, `done`, or `blocked`.

Keep at most one task `in_progress`. Mark a task `done` only after its outputs exist and its boundary-level check ran. A task may serve several acceptance criteria, and a criterion may require several tasks. Do not create nodes for commentary, planning prose, or work outside the approved scope.

## Scheduling

Select only a dependency-ready pending node. Prefer the smallest vertical slice that exposes integration risk early: route to rendering, rendering to state, state to persistence/provider boundary, then cross-cutting acceptance. Add a task only when new verified information creates required work; do not grow the graph from speculative improvements.

If a dependency fails, mark the affected node `blocked` and name the missing condition in the gate summary. Product ambiguity is `NEEDS_INPUT`, not an implementation task. A cycle, unknown dependency, self-dependency, missing output, or acceptance ID with no matching criterion is a contract failure.

## Resume behavior

Reload the manifest and verify the P6 digest before selecting a node. Reconcile task status against files and evidence: do not trust `done` when required outputs disappeared, and do not overwrite unrelated changes made outside P7. When the source handoff digest changes, stop and re-enter through intake.
