# Acceptance Contract

Read this before claiming completion. Acceptance proves the approved behavior in the target host; it is not a prose confidence statement.

## Mapping

Map every P6 acceptance criterion unchanged to a unique P7 acceptance ID with `source: "handoff"`. Add `derived` checks for architecture, integration, frontend, security, regression, or build behavior when needed. Derived checks may strengthen the gate but may not reinterpret source criteria.

Each acceptance entry has one status:

- `unverified`: not yet run;
- `pass`: observed result satisfies the criterion and durable evidence exists;
- `fail`: observed result violates the criterion;
- `blocked`: the check could not run because a named prerequisite is missing.

## Evidence

Evidence paths must exist inside the repository and identify what ran, against which revision/configuration, and the result. Suitable evidence includes a machine-readable test report, captured command output, screenshot for a visual claim, or a dated manual-check record for behavior that cannot be automated. Reusing one evidence file is allowed when it directly supports each mapped criterion.

Never mark a criterion `pass` from source inspection alone when it specifies runtime behavior. Never treat a skipped, unavailable, flaky, or partially run check as passing. Keep failures visible until a later run produces replacement evidence.

## COMMIT gate

`COMMIT` requires:

1. the P6 handoff and approved artifact are present and the pinned digest matches;
2. all tasks are `done` and their outputs exist;
3. all source and derived acceptance entries are `pass` with existing evidence;
4. applicable frontend states, accessibility checks, and responsive checks are recorded;
5. required security controls and trust boundaries are recorded;
6. the repository's relevant tests/build checks succeeded; and
7. `validate_p7.py` returns `valid: true`.

Deployment is a separate gate. A development `COMMIT` does not assert that hosting, DNS, production credentials, monitoring, backup, or rollback has been configured.
