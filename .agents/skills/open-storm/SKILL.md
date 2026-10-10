---
name: open-storm
description: Explore vague ideas through independent stakeholder perspectives, question storms, relay mutation, inversion, and cross-branch combinations. Use for open brainstorming and optional multi-model Council before the user requests convergence.
---

# Open Storm

Start with the user's words. One sentence is enough. Do not demand a completed Problem Frame, target user, metric, kill criterion, or product-manager framing before exploring. Unknowns are material for exploration, never established facts.

Use `python scripts/open_storm.py` from the repository root. `init --topic <text> --session <new.json>` starts a graph. `status` restores it. Read `docs/OPEN_STORM.md` for provider configuration and commands.

## Facilitation

- Select or introduce roles according to the activity: initiator, affected people, upside investors, liquidity providers, loss bearers, connectors, operators, and outsiders. These are examples, not a required panel. Describe incentives, resources, knowledge and blindspots. Never claim real professional identities or credentials.
- Roles and models are independent. Rotate creative operations across roles. A bank can invent bold alternatives and a risk bearer can invent conditions under which a proposal becomes possible.
- Begin independent generation without peer ideas. Subsequently expose selected parent ideas for relay mutation, inversion, or cross-branch combination. Record parents; do not silently erase unusual ideas or merge dissent into consensus.
- Choose operations according to the conversation, not a fixed sequence or number of rounds. Expand a stalled branch, combine promising distant branches, reframe the question when necessary.
- During exploration, avoid scores, rankings, elimination and funding verdicts. Pressure testing opens repair branches and does not erase parents. Apply any user-stated hard boundaries without demanding invented ones.

## Generative Grill

Use `question` for questions that open new possibilities: change who pays, who benefits, who owns, when resources arrive, or what failure means. Questions may address the user, another role, or an assumption. Keep unanswered questions open; they do not block unrelated branches. Offer the user participation, observation, and branch selection without forcing a questionnaire. `answer` creates a linked USER_STATEMENT, not independently verified evidence. User replies may generate multiple branches or revise the original topic through new questions.

## Execution and recovery

`prepare` builds an isolated prompt. Host Codex can respond with the JSON contract and use `import` to persist it; this needs no extra API credential. `round` explicitly invokes selected configured members, with all prompts snapshotted first. At present calls are sequential for bounded, recoverable execution; conceptual independence does not require concurrency. Real Council requires two successful distinct providers. Single-provider role simulation must be described honestly.

Save after each response. Provider failures and interrupted calls remain events, not knowledge. Do not automatically replay ambiguous calls. Never copy keys, subscriptions tokens or raw provider errors into session files. Configure desired flagship IDs explicitly; do not substitute defaults and claim flagship access.

## Convergence

When the user requests selection, use `converge --select <ids>`. Preserve other nodes and questions. This records the user's selection, not quality approval. `explore` reopens divergence. Export the graph as a space map, then use brainstorm-governor for evidence, complete decision framing and approved handoff where needed. Do not automatically enter implementation.
