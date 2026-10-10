# Brainstorm Governor Full Version Acceptance Report

- Status: `FULL_VERSION`
- Result: `PASS`
- Fingerprint: `version:v1:sha256:b7e1ec915895be9929106c7ee1656eab9c34b2a6509738b6b6425c76ef51ca9f`
- Finished: `2026-10-10T12:03:35.970378Z`
- xfail/xpass: `0`

## Acceptance Criteria

| AC | Result | Test | Evidence |
|---|---|---|---|
| AC-01 | PASS | `tests.acceptance.test_ac01_one_command.OneCommandAcceptanceTests.test_ac_01_single_command_reaches_legal_stop` | tests/acceptance/test_ac01_one_command.py, tests/acceptance/fixtures/ac01_one_command.json |
| AC-02 | PASS | `tests.acceptance.test_ac02_resume_matrix.ResumeMatrixAcceptanceTests.test_ac_02_every_stage_resumes_to_equivalent_main_state` | tests/acceptance/test_ac02_resume_matrix.py, tests/acceptance/fixtures/ac02_resume_matrix.json |
| AC-03 | PASS | `tests.acceptance.test_research_worker_isolation.ResearchWorkerIsolationAcceptanceTests.test_ac_03_research_and_worker_failures_do_not_pollute_main_state` | tests/acceptance/test_research_worker_isolation.py, tests/acceptance/fixtures/ac03_isolation_failure.json |
| AC-04 | PASS | `tests.acceptance.test_evaluator_artifact_gates.EvaluatorCapAcceptanceTests.test_ac_04_evaluator_calls_never_exceed_two_across_resume` | tests/acceptance/test_evaluator_artifact_gates.py, tests/acceptance/fixtures/ac04_evaluator_cap.json |
| AC-05 | PASS | `tests.acceptance.test_budget_park_matrix.BudgetParkMatrixAcceptanceTests.test_ac_05_every_stage_parks_before_work` | tests/acceptance/test_budget_park_matrix.py, tests/acceptance/fixtures/ac05_budget_exhaustion.json |
| AC-06 | PASS | `tests.acceptance.test_trace_usage.TraceUsageAcceptanceTests.test_ac_06_automatic_activation_and_real_usage_cost_trace` | tests/acceptance/test_trace_usage.py, tests/acceptance/fixtures/ac06_trace_usage.json |
| AC-07 | PASS | `tests.acceptance.test_version_upgrade.VersionUpgradeAcceptanceTests.test_ac_07_version_changes_require_non_mocked_live_regression` | tests/acceptance/test_version_upgrade.py, tests/acceptance/fixtures/ac07_version_upgrade.json |
| AC-08 | PASS | `tests.acceptance.test_evaluator_artifact_gates.ArtifactGateAcceptanceTests.test_ac_08_only_current_hash_matched_approved_artifact_can_handoff` | tests/acceptance/test_evaluator_artifact_gates.py, tests/acceptance/fixtures/ac08_artifact_gate.json |

## Release Gates

- clean_room: `PASS`
- all_acceptance_criteria: `PASS`
- p0_p6_regression: `PASS`
- version_regression_gate: `PASS`
- skill_validation: `PASS`
- xfail_xpass_zero: `PASS`

## Boundary

This report proves the checked-in local runtime and acceptance contracts. External Research, Worker, Evaluator, and Council Provider integrations remain deployment-specific and are not claimed by this report.
