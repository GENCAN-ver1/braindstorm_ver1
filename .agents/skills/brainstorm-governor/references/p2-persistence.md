# P2 Persistence and Re-entry Contract

P2 adds a durable Living Brief around the unchanged P0 state and P1 core loop. It does not infer state from chat history.

## Canonical source

`CONCEPT_BRIEF.md` is human-readable Markdown with a versioned fenced JSON block between stable markers. The JSON block is the canonical recovery source; rendered prose is an audit view only. Reject missing fields, unknown fields, malformed JSON, unsupported versions, or duplicated fields that disagree with `runtime_state`.

The contract stores the full validated P0 `runtime_state` plus:

- problem, target user, success metric, kill criterion, and constraints;
- locked concept, scope in, and scope out;
- assumptions split into validated and unvalidated sets;
- unknowns and open questions;
- evidence, risks, cheapest test, and exit status;
- append-only Decision Log entries;
- eliminated candidates with concise reasons;
- previous stop reason and the next action.

FV-02 stores one operational checkpoint record in `runtime_state.deferred`. Treat it as runtime-owned metadata, never as a candidate or user decision. Its versioned envelope records revision, run ID, completed/pending stage, in-flight operation, idempotency key, main-state hash, Trace cursor, evaluator count, numeric usage totals, usage receipt IDs, artifact status, operation receipts, idempotent budget charges, append-only operational failures, and recovery count.

## Save rules

Use `scripts/p2_persistence.py`. Save after every round with the current `stage`, `status`, and `next_action`. Writes use a same-directory temporary file followed by atomic replacement. If canonical content is unchanged, do not rewrite the file.

Full-cycle writes use `runtime/checkpoint.py`. Every mutation acquires the same-directory CAS lock, verifies both the expected revision and source-file digest, increments revision, recomputes the seven-field main-state hash, and then delegates to the P2 atomic writer. Reject stale writers; never merge concurrent checkpoint envelopes.

## Re-entry rules

1. Check for the Brief before running routing or brainstorming stages.
2. If it exists, restore and validate it first.
3. Resume from its persisted stage, status, open questions, assumption status, and previous stop reason.
4. Do not re-derive persisted `LOCKED` decisions.
5. Compare overlapping incoming state only to detect conflicts. Persisted state remains authoritative until an explicit update.
6. Report conflicts; never merge or overwrite them automatically.

The FV-02 restore order is fixed: load canonical Brief → validate P2 schema → parse the checkpoint envelope → verify `run_id` and `state_hash` → restore Trace/usage/evaluator counters → inspect any in-flight operation → resume `next_stage`. A legacy P2 Brief without a checkpoint must pass through `persistence/migrations/add_checkpoint_envelope_v1.py`; migration must preserve its runtime state and LOCKED decisions.

Use one stable idempotency key per `run_id + stage + operation_id`. Persist the in-flight record before an external call and its receipt before stage commit. On recovery, reuse an existing receipt; otherwise follow the explicit `RETRY`, `COLLECT`, or `PARK` policy. Never repeat a completed external side effect merely because the stage process was interrupted.

FV-03 charges one budget step before every stage body and before every external call. Persist the charge and updated `used_steps` atomically before work, and reuse its stable charge key after interruption. Saving `PARK` consumes no additional step. On exhaustion save `stage=STOPPED`, `status=STOPPED`, `exit_status=PARK`, keep `next_stage` set to the blocked stage, and make `next_action` name that stage. Re-entry must preserve `used_steps`; resume a budget `PARK` only after an explicit increase above the persisted `max_steps`.

FV-04 external work starts from a deep main-state snapshot and writes only to a transaction staging area. Persist each operational failure through the checkpoint CAS path before leaving the stage; recording a failure advances the Trace cursor but never creates evidence, candidates, recommendations, or decisions. Only a validated copy-on-write transaction result may replace the main state. Legacy checkpoint envelopes without `failure_ledger` remain readable and acquire the empty field on their next save.

FV-05 stores the append-only Trace separately at `<brief-path>.trace.json`. Every traced checkpoint advances `trace_cursor`, writes events carrying the checkpoint revision, and validates an existing Trace against `run_id + revision + trace_cursor` on restore. Usage receipts live in the Trace; the checkpoint keeps only their stable IDs and numeric totals for idempotent recovery. Legacy envelopes without `usage_receipt_ids` remain readable and acquire the empty field on their next save.

FV-06 persists evaluator reservation and consumption keys with `evaluator_rounds_used`, plus `artifact_status` and the current `quality_gate_id`. Reserve a round before Provider execution, reuse an unconsumed request or durable receipt after interruption, and reject a third reservation. An approved artifact must bind its manifest to the current run and Brief revision; advancing the Brief revision invalidates the old artifact for handoff. Legacy envelopes synthesize consumed legacy evaluator keys and leave `quality_gate_id` null until a new quality gate runs.

## Decision Log rules

P0 continues to reject silent changes to `LOCKED` decisions. The only P2 update path is `update_locked_decision`, which requires a non-empty reason and at least one evidence reference. It appends `old_value`, `new_value`, `reason`, and `evidence` before updating the restored state. Repeating an identical update is a no-op.

## Boundary

P2 does not perform external research, start sub-agents, invoke a Council, run an Evaluator, or enter implementation planning.
