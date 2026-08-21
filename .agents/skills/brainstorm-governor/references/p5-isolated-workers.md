# P5 Isolated Workers and Council Boundary

Read this reference only when the work may contain independently generatable dimensions. Use `scripts/p5_orchestration.py`; it defines a lightweight executor adapter and does not bind the governor to a thread pool, queue, model SDK, or orchestration framework.

## Parallel gate

Default to `parallelism=1`. Enable workers only when all conditions hold:

```text
independent_dimensions >= 2
outputs_independently_generatable = true
synthesis_cost < duplicated_context_cost
effective_parallelism >= 2
```

Spark and Shape remain single-agent unless the user explicitly requests parallel work. Never raise parallelism beyond the P0 run budget.

## Worker isolation

Exploration worker content contains only:

```text
shared_frame
assigned_lens
hard_constraints
candidate_output_schema
```

The orchestration wrapper adds only worker identity and kind. Submit every task before collecting any output, so no exploration worker can anchor on a peer result. Validate that candidates use the assigned lens and the canonical P1 candidate schema.

Each research worker receives exactly one `ResearchQuestion`. Validate its output through the P4 citation-support, numeric, and source-conflict contracts after collection.

## Main Agent ownership

Workers do not synthesize or converge. The main layer owns:

- candidate schema validation and mechanism-level deduplication;
- citation-support checks and source-conflict exposure;
- synthesis and final recommendation;
- whether one targeted supplemental round is allowed.

Submit or collect failures are recorded per worker. Valid results from other workers remain usable, and the main P0 state is unchanged until an explicit later synthesis/apply step.

`adapters/worker_runtime.py` executes the isolated worker batch behind one durable external-call receipt and gives P5 only a deep snapshot of main state. Returned candidates and evidence enter transaction staging before validation; workers never hold or mutate the canonical state. The default `validated-partial` policy commits only independent valid units in one copy-on-write result, while explicit `all-or-nothing` discards the whole batch after any failure. Recovery reuses the stored receipt instead of rerunning the executor. The adapter records the parallel gate and P5 activation automatically. A real executor should expose `usage_receipt() -> ProviderUsage`; absence is recorded as `UNAVAILABLE`, never zero.

## Council adapter

Council is not governor-core logic. It can be enabled only through a named external adapter after at least two independent agents succeed. When no real independent agents are active, label role-based views `PERSPECTIVE_LENSES`, never `COUNCIL`.

For DeepSeek, Kimi, or MiniMax provider configuration and normalized multi-provider results, read [p5-council-providers.md](p5-council-providers.md) and use `scripts/p5_council.py`. Provider credentials and raw responses remain outside governor state.

## Boundary

P5 does not introduce a heavyweight orchestration framework, run an Evaluator, or enter implementation planning. P6 owns evaluator, tracing, and regression gates.
