# Open Storm verification · 2026-10-10

## FDE acceptance revision (supersedes earlier blockers below)

The repository has no separate FDE standard. Acceptance covers initialization,
configuration, independent roles, generative questions, branch lineage, user answers,
durable recovery, provider failure isolation, explicit convergence, export and release.
Scope: local CLI and skill; creative quality and deployment provider access are separate.

Final checks: repository discovery 142 tests passed; focused Open Storm/Windows/Council
23 tests passed; P0-P6 contract 108 tests passed; full-version acceptance PASS (all six gates);
release gate ALLOW; new skill validator PASS; whitespace check PASS.

Text inputs use LF via `.gitattributes`, because release fingerprints hash bytes.
Reports are generated after normalization; re-running the gate before the full-version
report keeps the recorded gate-file hash consistent.

Final reruns reproduced Windows WinError 10053 in the existing Web host oversized-body
test. Before rejecting a body, the server now discards at most 64 KiB + 1 byte,
with a 0.25-second socket-read timeout, without parsing or forwarding it to the service.
This prevents the response being lost when closing a socket with a just-over-limit body.
A much larger or stalled rejected body can still end in connection termination;
the drain remains bounded. Added a bounded-drain test and reran the Web suite.

- Reproduce: `python acceptance/open_storm.py --live-codex --report acceptance/open-storm-report.json`.
  The report contains 18 passing lifecycle checks and a real ChatGPT subscription call.
  Synthetic public topic only; no API key used. Default model selection does not verify flagship access.
- Added corrupt-session validation, final-turn handling for Codex commentary,
  credential redirect rejection and bounded Windows atomic-replace retries.
  A permanent failure remains an error and preserves the previous file.
- Windows WinError 5 recurred at different legacy checkpoints. A transient sharing issue
  is the working hypothesis; the specific locking process has not been identified.
  Tests inject sharing/permanent errors and check the retry bound.
- Release evidence: `evals/live-report.json`, `evals/baseline-manifest.json`,
  `evals/gate-report.json`, `acceptance/report.json` and `acceptance/report.md`.
  Local runtime regression is distinct from external model evaluation.
  Baseline approval records the user's delegated FDE instruction and Codex as reviewer;
  it does not assert an independent human review.
- SSH repository read succeeded through `ssh.github.com:443`, with `HostKeyAlias=github.com`.
  Use a per-command `core.sshCommand` override; origin remains the requested SSH URL.
  The original checkout's unrelated edits and staged deletions are excluded from this branch.

Remaining deployment acceptance: configure DS/Kimi/GLM/Qwen endpoints, credentials and model IDs;
verify live multi-provider Council and flagship model access. Single writer only. Pending calls
require manual review before replay; no exactly-once external execution guarantee.
No Web UI integration or automatic financial-cost accounting is claimed.

## Earlier implementation checkpoint (historical)

## Executed

- RED: `python -m unittest tests.test_open_storm -v` initially failed because runtime/open_storm.py did not exist.
- Subsequent RED tests caught a custom-role CLI restriction and null API endpoint handling; both corrected and passing.
- Final focused run: Open Storm 11 tests and existing Council HTTP 6 tests passed.
- Existing P0–P6 offline contract regression: 108 tests passed (reported by `python ci/regression_gate.py check`).
- Root CLI `python scripts/brainstorm.py storm --help` works.
- `git diff --check` passed; Git reported CRLF conversion warnings.
- Live local Codex / ChatGPT subscription: successful call on a synthetic reading-group topic, yielding 9 validated idea nodes. Provider-reported usage: input_tokens 20006, cached_input_tokens 12544, output_tokens 618. Model ID was not explicitly pinned; this verifies subscription transport, not flagship access. No four-provider API call was made.

## Remaining boundaries

- Full repository discovery at that point ran 133 tests with 3 failures and 2 errors. Three failures depend on the release baseline; two errors were PermissionError/WinError 5 in the unchanged legacy P2 temporary-file os.replace path. A targeted rerun reproduced WinError 5 in that path at different checkpoints; OS-level cause has not been established.
- Release gate is BLOCK: governor_prompt and adapter fingerprints changed and no new approved live regression report was supplied. New skill, graph prompts and provider adapter are included in version-inputs.json. Offline contract tests pass. This local subscription smoke is not that report. Baseline approval was not fabricated.
- DS/Kimi/GLM/Qwen entrypoints are implemented with mocked HTTP tests; account endpoints, exact flagship IDs, credentials, and live compatibility await configuration.
- Local CLI/skill delivered; Web UI integration is outside this implementation. Session files are single-writer.
- Existing user changes and staged deletions were preserved. No commit, push or publishing was performed.

## SSH

Origin fetch/push now use `git@github.com:GENCAN-ver1/braindstorm_ver1.git`. With explicit user approval, GitHub's official Ed25519 host key was appended to `C:\Users\lenovo\.ssh\known_hosts` after verifying SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU. Repository read timed out; direct SSH handshake also timed out at the resolved address 198.18.0.77 even though TCP ports 22 and 443 were reachable. SSH authentication/repository access remain unverified; no client private key or account configuration was changed.
