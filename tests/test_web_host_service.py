from __future__ import annotations

import json
import shutil
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from adapters.deepseek_p1 import DeepSeekGenerationResult, DeepSeekProviderError
from runtime.governor_modules import p6
from web_host.service import BrainstormService, ServiceError


def _frames(*, missing: str | None = None) -> dict[str, object]:
    values = {
        "target_user": "Independent product teams",
        "core_task": "Turn a rough concept into testable options",
        "desired_change": "Choose one option with explicit tradeoffs",
        "hard_constraints": ["No external factual claims"],
        "success_metrics": ["One option reaches a Human Gate"],
        "abandonment_criteria": ["No option survives the constraints"],
        "non_goals": ["Production deployment"],
        "validation_horizon": "One week",
    }
    result = {}
    for key, value in values.items():
        result[key] = {
            "value": [] if key == missing and isinstance(value, list) else ("" if key == missing else value),
            "status": "UNKNOWN" if key == missing else "KNOWN",
            "source": "user",
        }
    return result


def _generated_payload() -> dict[str, object]:
    candidates = []
    challenges = []
    assessments = []
    for index, lens in enumerate(("BASELINE", "INVERSION", "SUBSTITUTION"), 1):
        candidate_id = f"c{index}"
        candidates.append(
            {
                "id": candidate_id,
                "title": f"Option {index}",
                "one_liner": f"A distinct governed option {index}",
                "core_mechanism": f"mechanism-{index}",
                "target_user": {"statement": "Independent product teams", "classification": "KNOWN"},
                "value_created": f"Value {index}",
                "why_distinct": f"Distinct mechanism {index}",
                "key_assumptions": [{"statement": f"Assumption {index}", "classification": "ASSUMPTION"}],
                "main_dependency": {"statement": f"Dependency {index}", "classification": "ASSUMPTION"},
                "exploration_lens": lens,
                "complexity": "LOW" if index == 1 else "MEDIUM",
            }
        )
        challenges.append(
            {
                "candidate_id": candidate_id,
                "blindspots": [f"Blindspot {index}"],
                "assumption_audit": [{"statement": f"Audit {index}", "classification": "ASSUMPTION"}],
                "pressure_test": [f"Pressure test {index}"],
            }
        )
        assessments.append(
            {
                "candidate_id": candidate_id,
                "hard_constraint_violations": [],
                "user_value": 1.0 if index == 1 else 0.5,
                "feasibility": 1.0 if index == 1 else 0.5,
                "evidence_confidence": 0.8 if index == 1 else 0.4,
                "reversibility": 0.9 if index == 1 else 0.5,
                "risk": 0.1 if index == 1 else 0.5,
            }
        )
    return {
        "candidates": candidates,
        "challenges": challenges,
        "assessments": assessments,
        "recommended_candidate_id": "c1",
        "confidence": 0.82,
        "cheapest_test": "Prototype c1 with three users.",
    }


class FakeGenerator:
    def __init__(self, payload: dict[str, object] | None = None, *, failure: Exception | None = None) -> None:
        self.payload = payload or _generated_payload()
        self.failure = failure
        self.calls = 0

    def generate(self, data_only_payload, *, operation_id):
        self.calls += 1
        if self.failure:
            raise self.failure
        self.last_input = data_only_payload
        self.last_operation_id = operation_id
        return DeepSeekGenerationResult(
            self.payload,
            {
                "provider": "deepseek",
                "model": "deepseek-v4-pro",
                "request_id": "req-test",
                "prompt_tokens": 100,
                "completion_tokens": 200,
                "total_tokens": 300,
                "latency_ms": 12.5,
            },
        )


class SlowGenerator(FakeGenerator):
    def generate(self, data_only_payload, *, operation_id):
        time.sleep(0.05)
        return super().generate(data_only_payload, operation_id=operation_id)


class PassingEvaluator:
    def __init__(self) -> None:
        self.calls = 0

    def evaluate(self, request):
        self.calls += 1
        self.last_request = request
        return p6.EvaluatorInvocation(p6.EvaluationReport([]), p6.RuntimeUsage())


class WebHostServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        test_root = Path.cwd() / "var" / "tests"
        test_root.mkdir(parents=True, exist_ok=True)
        self.root = test_root / f"web-host-{uuid.uuid4().hex}"
        self.root.mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(self.root)

    def _create(self, service: BrainstormService, *, missing: str | None = None):
        return service.create_session({"idea": "A governed ideation tool", "mode": "Spark", "frames": _frames(missing=missing)})

    def test_real_run_is_schema_validated_persisted_and_idempotent(self) -> None:
        generator = FakeGenerator()
        service = BrainstormService(self.root, generator=generator, evaluator=PassingEvaluator())
        created = self._create(service)
        first = service.start_run(created["id"], created["revision"])
        duplicate = service.start_run(created["id"], created["revision"])
        refreshed = service.start_run(first["id"], first["revision"])

        self.assertEqual(generator.calls, 1)
        self.assertEqual(first, duplicate)
        self.assertEqual(first, refreshed)
        self.assertEqual(first["governorStatus"], "ITERATE")
        self.assertEqual(first["review"]["recommendation"], "c1")
        self.assertEqual(first["review"]["usage"]["prompt_tokens"], 100)
        self.assertTrue((self.root / created["id"] / "living_brief.md").is_file())

    def test_concurrent_duplicate_start_is_billed_once(self) -> None:
        generator = SlowGenerator()
        service = BrainstormService(self.root, generator=generator, evaluator=PassingEvaluator())
        created = self._create(service)
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda _index: service.start_run(created["id"], 0),
                    range(2),
                )
            )
        self.assertEqual(generator.calls, 1)
        self.assertEqual(results[0], results[1])

    def test_missing_frames_do_not_call_provider_and_can_resume(self) -> None:
        generator = FakeGenerator()
        service = BrainstormService(self.root, generator=generator, evaluator=PassingEvaluator())
        created = self._create(service, missing="target_user")
        waiting = service.start_run(created["id"], 0)
        refreshed_waiting = service.start_run(created["id"], waiting["revision"])
        resumed = service.resume_run(
            created["id"],
            waiting["revision"],
            {"field": "target_user", "value": "Solo founders", "status": "KNOWN"},
        )

        self.assertEqual(generator.calls, 0)
        self.assertEqual(waiting["governorStatus"], "NEEDS_INPUT")
        self.assertEqual(waiting, refreshed_waiting)
        self.assertEqual(resumed["governorStatus"], "EXPLORE")

    def test_invalid_model_schema_is_safe_and_does_not_advance_revision(self) -> None:
        service = BrainstormService(self.root, generator=FakeGenerator({"candidates": []}), evaluator=PassingEvaluator())
        created = self._create(service)
        with self.assertRaisesRegex(ServiceError, "invalid governed response") as caught:
            service.start_run(created["id"], 0)
        self.assertEqual(caught.exception.code, "PROVIDER_FAILURE")
        persisted = json.loads((self.root / created["id"] / "session.json").read_text(encoding="utf-8"))
        self.assertEqual(persisted["revision"], 0)
        self.assertNotIn("governor_state", persisted)
        self.assertEqual(len(persisted["usage"]), 1)
        self.assertEqual(persisted["usage"][0]["request_id"], "req-test")

    def test_provider_failure_is_redacted_and_not_replayed(self) -> None:
        generator = FakeGenerator(failure=DeepSeekProviderError("provider request failed"))
        service = BrainstormService(
            self.root,
            generator=generator,
            evaluator=PassingEvaluator(),
        )
        created = self._create(service)
        with self.assertRaises(ServiceError) as caught:
            service.start_run(created["id"], 0)
        self.assertFalse(caught.exception.retryable)
        self.assertEqual(str(caught.exception), "provider request failed")
        with self.assertRaisesRegex(ServiceError, "cannot be replayed automatically"):
            service.start_run(created["id"], 0)
        self.assertEqual(generator.calls, 1)

    def test_human_confirm_runs_bounded_evaluator_before_commit(self) -> None:
        evaluator = PassingEvaluator()
        service = BrainstormService(self.root, generator=FakeGenerator(), evaluator=evaluator)
        created = self._create(service)
        review = service.start_run(created["id"], 0)
        committed = service.submit_human_gate(created["id"], review["revision"], {"kind": "confirm"})
        duplicate = service.submit_human_gate(created["id"], review["revision"], {"kind": "confirm"})

        self.assertEqual(evaluator.calls, 1)
        self.assertEqual(committed, duplicate)
        self.assertEqual(committed["governorStatus"], "COMMIT")
        handoff = service.get_handoff(created["id"])
        self.assertIsNotNone(handoff)
        self.assertIn("concept: c1", handoff["locked_decisions"])


if __name__ == "__main__":
    unittest.main()
