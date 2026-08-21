# P1 Single-Agent Core Loop

Read this reference after P0 routing selects a mode and the request needs more than routing alone.

## Stage contract

1. **Context** — extract `requested_outcome`, `current_idea`, `target_user`, `constraints`, `questions`, `alternatives`, and `assets`. Classify every uncertain item as `ASSUMPTION`, `UNKNOWN`, or `CONFLICT`; never promote it to `KNOWN` without evidence.
2. **Frame** — provide `problem_statement`, `target_user`, `job_to_be_done`, `desired_change`, `hard_constraints`, `soft_preferences`, `success_metric`, `kill_criterion`, `non_goals`, and `time_horizon`. If a critical field is `UNKNOWN`, stop with `NEEDS_INPUT`.
3. **Diverge** — use the three to five lenses returned by `select_exploration_lenses`. Generate candidates independently of evaluation. Candidate data must not contain `score` or `rank`, and the set must include one low-complexity option plus one inversion or substitution option.
4. **Normalize** — deduplicate by normalized `core_mechanism`, cluster by exploration lens, retain single-member outliers, and report coverage gaps. At most one targeted supplemental divergence round is allowed.
5. **Challenge** — keep `blindspots`, `assumption_audit`, and `pressure_test` separate. Run it only after Normalize. Challenge may add assumptions or unknowns but cannot edit the confirmed frame.
6. **Converge** — remove candidates with hard-constraint violations, then run Pareto dominance across user value, feasibility, evidence confidence, reversibility, and risk. Keep up to three non-dominated directions. Do not invent a recommendation when trade-offs do not justify one.
7. **Human Gate** — return recommendation, confidence, decisive assumptions, risks, cheapest test, and exit status. A recommendation stops at `NEEDS_INPUT` for user confirmation; no surviving candidate yields `ITERATE`; no single justified winner yields `EXPLORE`.

## Runtime usage

The single Agent prepares one structured request and passes it through:

```text
python scripts/p1_core.py run < request.json
```

The runtime is provider-neutral and performs no network or model calls. It rejects illegal stage order, implicit fact promotion, divergence score/rank fields, repeated supplemental rounds, incomplete challenges or assessments, invalid recommendations, and budget overflow.

## Candidate contract

Each candidate contains:

```text
id
title
one_liner
core_mechanism
target_user
value_created
why_distinct
key_assumptions
main_dependency
exploration_lens
complexity
```

`target_user`, `key_assumptions`, and `main_dependency` carry explicit knowledge classifications. Assessment dimensions exist only in the Converge input; they must never be added to candidate generation output.

## Scope boundary

P1 keeps all state in memory. Do not create or update `CONCEPT_BRIEF.md`, search external sources, spawn workers, consult external models, or run iterative evaluator passes.
