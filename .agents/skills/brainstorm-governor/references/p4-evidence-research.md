# P4 Evidence and Research Contract

Read this reference only when a claim may require external verification. Use `scripts/p4_research.py`; retrieval providers remain outside the governor core.

## Research Gate

Require research for unresolved claims about market, competitors, price, law, policy, standards, current APIs, current product capability, user/growth/behavior data, or another decisive external claim. Local preferences and subjective design choices do not trigger research.

If research is required but disabled or unavailable, stop safely with `RESEARCH_REQUIRED`. Do not replace missing evidence with model knowledge.

## Provider boundary

A provider implements one method:

```text
research(question) -> ProviderResearchResult
```

The provider owns search, page retrieval, and summarization. It returns only validated-shape evidence summaries and numeric claims. Raw search results, page dumps, and provider-specific payloads never enter the governor state or Living Brief. Use `provider_result_to_dict` and `provider_result_from_dict` as the normalized durable-receipt codec. P4 executes questions sequentially; parallel research belongs to P5.

A separate citation-support checker decides whether the supplied source excerpt actually supports the corresponding evidence claim. Retrieval success alone is not evidence acceptance.

## Evidence record

Each summary stores:

```text
id
question_id
claim
source
source_date
retrieved_at
evidence_strength
contradictions
confidence
supporting_excerpt
numeric_claim_ids
```

Time-sensitive claims require a dated source. Contradiction links must be reciprocal. Conflicted records remain `CONFLICT` and cannot be silently promoted to downstream facts.

## Numeric claims

The only numeric statuses are:

- `CITED`: numeric value plus at least one validated citation;
- `ESTIMATE`: numeric value plus a non-empty derivation basis;
- `UNKNOWN`: null value, never usable downstream as fact.

An evidence claim containing a numeric value must link an explicit NumericClaim; bare numbers are rejected.

## Persistence and downstream use

Validated summaries are adapted into P0 `evidence[]` with full P4 data stored in metadata, so P2 persists them without raw results. Citation-backed records become `KNOWN`; source conflicts become `CONFLICT`; estimates remain `ASSUMPTION`; unresolved numbers remain `UNKNOWN`.

`adapters/research_runtime.py` wraps provider calls with durable receipts and a copy-on-write `StateTransaction`. Each question is one atomic staging unit. Schema, numeric, citation, source-conflict, and knowledge-state validation must finish before that unit becomes committable. The default policy keeps independently validated units (`validated-partial`); callers may require `all-or-nothing`. Provider or validation failures go only to the operational failure ledger and can never enter `evidence[]`. The adapter records the research gate and P4 activation automatically. A provider may return `ObservedExternalResult(payload, ProviderUsage)`; otherwise the call receives an `UNAVAILABLE` usage receipt rather than estimated tokens.

Before Convergence, validate every evidence and numeric ID requested as a fact. Reject conflicted evidence and UNKNOWN numeric claims. Research/provider failure may preserve already validated summaries only under the active transaction policy and exits `RESEARCH_REQUIRED` while unresolved questions remain.

## Boundary

P4 does not start parallel research workers, spawn sub-agents, invoke a Council, run an Evaluator, or enter implementation planning.
