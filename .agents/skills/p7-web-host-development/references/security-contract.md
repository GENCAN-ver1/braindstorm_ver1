# Security Contract

Read this before implementing or changing a trust boundary. Security controls must match observed data and flows; do not claim controls merely because a framework offers them.

## Baseline controls

Every web implementation records these controls:

- `input-validation`: validate untrusted input at the enforcing boundary, including type, size, and allowed values;
- `output-encoding`: render into the correct output context and avoid unsafe HTML or command construction;
- `secret-management`: keep secret values out of source, manifests, logs, client bundles, URLs, and acceptance evidence;
- `dependency-review`: use the host lockfile and record the relevant dependency or build check.

When `auth_required` is true, also record `authentication`, `authorization`, and `session-protection`. Authorization is enforced server-side for every protected object/action; UI hiding is not authorization. Use the host's established identity system unless the approved handoff explicitly requires a change.

## Trust and data

Classify handled data as `public`, `internal`, `confidential`, or `restricted`. List each crossing such as browser-to-host, host-to-database, or host-to-provider in `trust_boundaries`. Minimize collection, persistence, logging, and return values at each crossing. Product analytics, tracking, or third-party transmission not present in the approved handoff is out of scope.

`secret_sources` contains environment-variable names only, matching `^[A-Z][A-Z0-9_]*$`; never record a value, assignment, URL credential, or example token. Do not create, rotate, or transmit real credentials without explicit authorization.

## Failure and stop conditions

Fail closed for authorization decisions and integrity checks. Preserve a usable safe path for ordinary availability failures. A known exploitable trust-boundary defect, leaked credential, missing required authorization check, or unreviewed destructive migration blocks `COMMIT`. Report the affected boundary and evidence without reproducing secrets.
