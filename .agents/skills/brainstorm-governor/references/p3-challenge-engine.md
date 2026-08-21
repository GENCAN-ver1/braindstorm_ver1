# P3 Challenge Engine Contract

Read this reference when the workflow needs a pre-divergence context audit or reaches Challenge after Normalize. Use `scripts/p3_challenge.py`; it performs no research and calls no other agents.

## Three isolated passes

1. **Blindspot** discovers omitted context. It cannot eliminate candidates or assign fatal/repairable outcomes.
2. **Assumption Audit** records each claim with an explicit `KNOWN`, `ASSUMPTION`, `UNKNOWN`, or `CONFLICT` classification. A `KNOWN` claim requires a local evidence reference.
3. **Pressure Test** attacks the registered assumptions and dependencies. It runs a Steelman before assigning any fatal outcome.

Do not let any pass edit the confirmed Problem Frame.

## Conditional pre-divergence pass

Run the pre-pass only during Context or Frame. It triggers when at least one signal is present:

- unfamiliar domain;
- UNKNOWN density at or above the configured threshold;
- elevated hidden-norm, stakeholder/incentive, or technical-constraint risk;
- explicit user request.

When triggered, provide `landmines`, `hidden_context`, `what_good_looks_like`, and `expert_questions`. When no trigger fires, return an empty pass instead of manufacturing concerns.

## Candidate Blindspot checklist

Check every normalized candidate against all categories:

- stakeholders;
- incentive mismatch;
- onboarding versus long-term use;
- adoption, migration, and exit cost;
- operator burden;
- second-order effects;
- legal, security, privacy, and reputation;
- external dependencies.

A checked category may have no finding. Blindspot findings retain an explicit knowledge classification; a `KNOWN` finding requires evidence.

## Assumption Register

Each record contains `claim`, `type`, `importance`, `confidence`, `evidence`, `failure_impact`, and `cheapest_test`. Supported types are desirability, feasibility, viability, adoption, distribution, operations, and timing.

Prioritize assumptions whose importance meets the high threshold and whose confidence is at or below the low threshold. Sort higher importance first, then lower confidence. Preserve all other assumptions in the register.

## Pressure Test suite

Run exactly one check for each type: pre-mortem, counterexample, boundary test, dependency failure, adoption friction, sustainability, substitute test, and Steelman. A repairable result requires a repair action. A fatal result is rejected if Steelman has not already run.

The engine derives `fatal_risks`, `repairable_risks`, and `evidence_gaps`. These outputs inform Convergence; P3 itself does not eliminate candidates.

## Boundary

P3 uses only supplied context and local evidence references. It does not retrieve external facts, spawn workers, invoke a Council, run an Evaluator, or enter implementation planning.

