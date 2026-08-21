from __future__ import annotations

import tempfile
import unittest
import uuid
from collections import Counter
from pathlib import Path

from runtime.checkpoint import CheckpointStore
from runtime.fault_injection import (
    FaultAction,
    FaultInjector,
    FaultPoint,
    FaultRule,
    InjectedInterruption,
    Stage,
)
from runtime.governor_modules import p0
from runtime.reentry import DurableStageRunner
from runtime.state_fingerprint import fingerprint_state


class DeterministicHandler:
    def __init__(self):
        self.calls = Counter()

    def __call__(self, stage, state, context):
        self.calls[stage.value] += 1
        state.candidates.append(
            {
                "id": f"stage-{stage.value.casefold()}",
                "core_mechanism": f"durable-{stage.value.casefold()}",
            }
        )
        p0.validate_state(state)
        return state


class ResumeMatrixMixin:
    def temp_path(self):
        path = Path(tempfile.gettempdir()) / f"brainstorm-{uuid.uuid4().hex}-ac02.md"
        self.addCleanup(path.unlink, missing_ok=True)
        self.addCleanup(
            path.with_name(f".{path.name}.cas.lock").unlink,
            missing_ok=True,
        )
        return path

    def state(self, run_id):
        state = p0.new_state(
            p0.RoutingInput(
                explicit_mode=p0.Mode.DECIDE,
                research_allowed=True,
                budget=p0.Budget(max_steps=128, max_parallelism=1),
            ),
            run_id=run_id,
        )
        state.decisions = [
            p0.Decision(
                id="concept",
                topic="locked_concept",
                value="checkpoint-first",
                status=p0.DecisionStatus.LOCKED,
                rationale="must survive recovery",
            )
        ]
        p0.validate_state(state)
        return state


class ResumeMatrixAcceptanceTests(ResumeMatrixMixin, unittest.TestCase):
    def test_ac_02_every_stage_resumes_to_equivalent_main_state(self):
        baseline_path = self.temp_path()
        baseline = DurableStageRunner(DeterministicHandler()).run(
            str(baseline_path), self.state("run-ac02")
        )
        baseline_fingerprint = fingerprint_state(p0.state_to_dict(baseline.state))

        for stage in Stage:
            for point in (
                FaultPoint.BEFORE_ENTER,
                FaultPoint.AFTER_CHECKPOINT,
                FaultPoint.BEFORE_COMMIT,
            ):
                with self.subTest(stage=stage.value, point=point.value):
                    path = self.temp_path()
                    handler = DeterministicHandler()
                    runner = DurableStageRunner(
                        handler,
                        fault_injector=FaultInjector(
                            [
                                FaultRule(
                                    stage,
                                    point,
                                    FaultAction.INTERRUPT,
                                )
                            ]
                        ),
                    )
                    with self.assertRaises(InjectedInterruption):
                        runner.run(str(path), self.state("run-ac02"))
                    self.assertTrue(path.is_file())

                    resumed = DurableStageRunner(handler).run(
                        str(path), self.state("incoming-state-is-not-authoritative")
                    )
                    self.assertTrue(resumed.resumed)
                    self.assertEqual(
                        fingerprint_state(p0.state_to_dict(resumed.state)),
                        baseline_fingerprint,
                    )
                    self.assertEqual(
                        resumed.state.decisions[0].value,
                        "checkpoint-first",
                    )
                    self.assertEqual(resumed.envelope.last_completed_stage, "COMMIT")
                    self.assertIsNone(resumed.envelope.next_stage)
                    self.assertGreaterEqual(resumed.envelope.recovery_count, 1)

    def test_checkpoint_progress_counters_remain_continuous_after_resume(self):
        path = self.temp_path()
        session = CheckpointStore().open(path, self.state("run-ac02-progress"))
        session.update_progress(
            trace_cursor=19,
            evaluator_rounds_used=1,
            usage_totals={"prompt_tokens": 120, "completion_tokens": 35},
            artifact_status="PENDING",
        )
        handler = DeterministicHandler()
        interrupted = DurableStageRunner(
            handler,
            fault_injector=FaultInjector(
                [
                    FaultRule(
                        Stage.EVALUATE,
                        FaultPoint.AFTER_CHECKPOINT,
                        FaultAction.INTERRUPT,
                    )
                ]
            ),
        )
        with self.assertRaises(InjectedInterruption):
            interrupted.run(str(path), self.state("ignored"))
        resumed = DurableStageRunner(handler).run(str(path), self.state("ignored-again"))
        self.assertEqual(resumed.envelope.trace_cursor, 19)
        self.assertEqual(resumed.envelope.evaluator_rounds_used, 1)
        self.assertEqual(resumed.envelope.usage_totals["prompt_tokens"], 120)
        self.assertEqual(resumed.envelope.artifact_status, "PENDING")


if __name__ == "__main__":
    unittest.main()

