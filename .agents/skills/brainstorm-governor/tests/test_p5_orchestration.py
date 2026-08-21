from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import unittest
from dataclasses import fields
from pathlib import Path


SKILL_ROOT = Path(__file__).parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"
P0_PATH = SCRIPTS_DIR / "p0_runtime.py"
P1_PATH = SCRIPTS_DIR / "p1_core.py"
P4_PATH = SCRIPTS_DIR / "p4_research.py"
P5_PATH = SCRIPTS_DIR / "p5_orchestration.py"
sys.path.insert(0, str(SCRIPTS_DIR))


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


p0 = load_module("p0_runtime", P0_PATH)
p1 = load_module("p1_core", P1_PATH)
p4 = load_module("p4_research", P4_PATH)
p5 = load_module("p5_orchestration", P5_PATH)


class MockExecutor:
    def __init__(self, results):
        self.results = results
        self.opened_with = None
        self.submitted = []
        self.collected = []

    def open(self, max_parallelism):
        self.opened_with = max_parallelism

    def submit(self, task):
        if self.collected:
            raise AssertionError("collection started before all tasks were submitted")
        self.submitted.append(copy.deepcopy(task))
        return f"handle:{task.id}"

    def collect(self, handle):
        worker_id = handle.split(":", 1)[1]
        self.collected.append(worker_id)
        result = self.results[worker_id]
        if isinstance(result, Exception):
            raise result
        return copy.deepcopy(result)


class StaticCitationChecker:
    def __init__(self, supported=True):
        self.supported = supported

    def supports(self, claim, source, supporting_excerpt):
        return self.supported


class P5FixtureMixin:
    def state(self, mode=p0.Mode.DECIDE, *, parallelism=3):
        state = p0.new_state(
            p0.RoutingInput(
                explicit_mode=mode,
                requested_parallelism=parallelism,
                budget=p0.Budget(max_parallelism=max(1, parallelism)),
            ),
            run_id=f"run-{mode.value.lower()}",
        )
        state.run.stage = p0.Stage.DIVERGE
        state.run.status = p0.RunStatus.ACTIVE
        state.frame.problem = p0.KnowledgeItem(
            "generate distinct solution mechanisms", p0.KnowledgeStatus.KNOWN
        )
        state.frame.user = p0.KnowledgeItem(
            "independent product builder", p0.KnowledgeStatus.KNOWN
        )
        state.frame.constraints = [
            p0.KnowledgeItem(
                "must remain reversible", p0.KnowledgeStatus.KNOWN
            )
        ]
        p0.validate_state(state)
        return state

    def signals(self, *, explicit=False):
        return p5.ParallelGateSignals(
            independent_dimensions=3,
            outputs_independently_generatable=True,
            synthesis_cost=1.0,
            duplicated_context_cost=3.0,
            explicit_parallel_request=explicit,
        )

    def assignments(self):
        return [
            p5.ExplorationAssignment("worker-baseline", p1.ExplorationLens.BASELINE),
            p5.ExplorationAssignment("worker-analogy", p1.ExplorationLens.ANALOGY),
            p5.ExplorationAssignment(
                "worker-substitution", p1.ExplorationLens.SUBSTITUTION
            ),
        ]

    def exploration_tasks(self, count=3):
        return p5.build_exploration_tasks(
            self.state(),
            self.assignments()[:count],
            hard_constraints=["must remain reversible"],
        )

    def candidate(self, candidate_id, lens, mechanism):
        candidate = p1.Candidate(
            id=candidate_id,
            title=f"Option {candidate_id}",
            one_liner=f"A direction for {candidate_id}",
            core_mechanism=mechanism,
            target_user=p0.KnowledgeItem(
                "independent product builder", p0.KnowledgeStatus.KNOWN
            ),
            value_created=f"Value from {candidate_id}",
            why_distinct=f"Distinct mechanism {candidate_id}",
            key_assumptions=[
                p0.KnowledgeItem(
                    f"users accept {candidate_id}", p0.KnowledgeStatus.ASSUMPTION
                )
            ],
            main_dependency=p0.KnowledgeItem(
                f"dependency for {candidate_id}", p0.KnowledgeStatus.UNKNOWN
            ),
            exploration_lens=lens,
            complexity=p1.CandidateComplexity.LOW,
        )
        return p1._json_ready(candidate)

    def exploration_success(self, worker_id, lens, candidate_id, mechanism):
        return p5.WorkerExecutionResult(
            worker_id=worker_id,
            kind=p5.WorkerKind.EXPLORATION,
            success=True,
            output=p5.ExplorationWorkerOutput(
                [self.candidate(candidate_id, lens, mechanism)]
            ),
        )

    def question(self, question_id="q1"):
        return p4.ResearchQuestion(
            id=question_id,
            claim="The current product supports offline mode",
            category=p4.ResearchCategory.PRODUCT_CAPABILITY,
            time_sensitive=True,
        )

    def evidence(self, evidence_id="e1", contradictions=None):
        return p4.ResearchEvidenceRecord(
            id=evidence_id,
            question_id="q1",
            claim=(
                "The current product supports offline mode"
                if evidence_id == "e1"
                else "The current product requires a network connection"
            ),
            source=f"https://docs.example.test/{evidence_id}",
            source_date="2026-08-19",
            retrieved_at="2026-08-20T12:00:00+08:00",
            evidence_strength=p4.EvidenceStrength.HIGH,
            contradictions=[] if contradictions is None else contradictions,
            confidence=0.90,
            supporting_excerpt="The current capability is documented here.",
        )


class ParallelGateTests(P5FixtureMixin, unittest.TestCase):
    def test_parallel_gate_false_for_simple_shape_without_explicit_request(self):
        state = self.state(p0.Mode.SHAPE, parallelism=3)

        decision = p5.parallel_gate(state, self.signals(explicit=False))

        self.assertFalse(decision.enabled)
        self.assertEqual(decision.effective_parallelism, 1)
        self.assertIn("Shape remains single-agent", " ".join(decision.reasons))

    def test_parallel_gate_true_when_all_conditions_hold(self):
        decision = p5.parallel_gate(self.state(), self.signals())

        self.assertTrue(decision.enabled)
        self.assertEqual(decision.effective_parallelism, 3)

    def test_default_parallelism_one_keeps_gate_closed(self):
        decision = p5.parallel_gate(
            self.state(parallelism=1), self.signals(explicit=True)
        )

        self.assertFalse(decision.enabled)
        self.assertIn("defaults to 1", " ".join(decision.reasons))

    def test_gate_cli(self):
        payload = {
            "state": p0.state_to_dict(self.state()),
            "signals": p5._json_ready(self.signals()),
        }
        result = subprocess.run(
            [sys.executable, str(P5_PATH), "gate"],
            input=json.dumps(payload),
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["enabled"])


class WorkerIsolationTests(P5FixtureMixin, unittest.TestCase):
    def test_workers_receive_minimal_isolated_payloads(self):
        tasks = self.exploration_tasks()
        results = {
            "worker-baseline": self.exploration_success(
                "worker-baseline", p1.ExplorationLens.BASELINE, "c1", "guided interview"
            ),
            "worker-analogy": self.exploration_success(
                "worker-analogy", p1.ExplorationLens.ANALOGY, "c2", "design studio"
            ),
            "worker-substitution": self.exploration_success(
                "worker-substitution",
                p1.ExplorationLens.SUBSTITUTION,
                "c3",
                "replace workshop with checklist",
            ),
        }
        executor = MockExecutor(results)

        outcome = p5.orchestrate_workers(
            self.state(), self.signals(), tasks, executor
        )

        self.assertEqual(executor.opened_with, 3)
        self.assertEqual(len(executor.submitted), 3)
        self.assertEqual(len(executor.collected), 3)
        for task in executor.submitted:
            self.assertEqual(
                {item.name for item in fields(task.payload)},
                {
                    "shared_frame",
                    "assigned_lens",
                    "hard_constraints",
                    "candidate_output_schema",
                },
            )
            self.assertFalse(hasattr(task.payload, "peer_results"))
        self.assertEqual(len(outcome.normalized_candidates), 3)
        self.assertTrue(outcome.state_unchanged)

    def test_each_research_worker_receives_exactly_one_question(self):
        tasks = p5.build_research_tasks([self.question("q1"), self.question("q2")])

        self.assertEqual(len(tasks), 2)
        self.assertTrue(all(len(fields(task.payload)) == 1 for task in tasks))
        self.assertEqual(
            [task.payload.question.id for task in tasks], ["q1", "q2"]
        )


class FailureAndNormalizeTests(P5FixtureMixin, unittest.TestCase):
    def test_partial_worker_failure_preserves_main_state(self):
        tasks = self.exploration_tasks(count=2)
        results = {
            "worker-baseline": self.exploration_success(
                "worker-baseline", p1.ExplorationLens.BASELINE, "c1", "guided interview"
            ),
            "worker-analogy": p5.WorkerExecutionResult(
                worker_id="worker-analogy",
                kind=p5.WorkerKind.EXPLORATION,
                success=False,
                error="worker timeout",
            ),
        }
        state = self.state()
        before = p0.state_to_dict(copy.deepcopy(state))

        outcome = p5.orchestrate_workers(
            state, self.signals(), tasks, MockExecutor(results)
        )

        self.assertEqual(outcome.successful_worker_ids, ["worker-baseline"])
        self.assertIn("worker-analogy", outcome.failed_workers)
        self.assertEqual(len(outcome.normalized_candidates), 1)
        self.assertEqual(outcome.second_round.status, p5.SecondRoundStatus.ALLOWED)
        self.assertFalse(outcome.synthesis_ready)
        self.assertEqual(p0.state_to_dict(state), before)
        self.assertTrue(outcome.state_unchanged)

    def test_duplicate_worker_results_are_normalized_before_synthesis(self):
        tasks = self.exploration_tasks(count=2)
        results = {
            "worker-baseline": self.exploration_success(
                "worker-baseline", p1.ExplorationLens.BASELINE, "c1", "guided interview"
            ),
            "worker-analogy": self.exploration_success(
                "worker-analogy",
                p1.ExplorationLens.ANALOGY,
                "c2",
                "Guided interview!!!",
            ),
        }

        outcome = p5.orchestrate_workers(
            self.state(), self.signals(), tasks, MockExecutor(results)
        )

        self.assertEqual([item.id for item in outcome.normalized_candidates], ["c1"])
        self.assertEqual(len(outcome.eliminated_duplicates), 1)
        self.assertIn(
            "duplicate core mechanism", outcome.eliminated_duplicates[0].reason
        )
        self.assertIn("ANALOGY", outcome.coverage_gaps)

    def test_main_layer_rechecks_research_citation_support(self):
        research_task = p5.build_research_tasks([self.question()])[0]
        exploration_task = self.exploration_tasks(count=1)[0]
        results = {
            exploration_task.id: self.exploration_success(
                exploration_task.id,
                p1.ExplorationLens.BASELINE,
                "c1",
                "guided interview",
            ),
            research_task.id: p5.WorkerExecutionResult(
                worker_id=research_task.id,
                kind=p5.WorkerKind.RESEARCH,
                success=True,
                output=p5.ResearchWorkerOutput(
                    p4.ProviderResearchResult([self.evidence()], [])
                ),
            ),
        }

        outcome = p5.orchestrate_workers(
            self.state(),
            self.signals(),
            [exploration_task, research_task],
            MockExecutor(results),
            citation_checker=StaticCitationChecker(False),
        )

        self.assertIn(research_task.id, outcome.failed_workers)
        self.assertEqual(outcome.evidence, [])
        self.assertIn("does not support claim", outcome.failed_workers[research_task.id])

    def test_main_layer_exposes_source_conflicts(self):
        research_task = p5.build_research_tasks([self.question()])[0]
        exploration_task = self.exploration_tasks(count=1)[0]
        first = self.evidence("e1", ["e2"])
        second = self.evidence("e2", ["e1"])
        results = {
            exploration_task.id: self.exploration_success(
                exploration_task.id,
                p1.ExplorationLens.BASELINE,
                "c1",
                "guided interview",
            ),
            research_task.id: p5.WorkerExecutionResult(
                worker_id=research_task.id,
                kind=p5.WorkerKind.RESEARCH,
                success=True,
                output=p5.ResearchWorkerOutput(
                    p4.ProviderResearchResult([first, second], [])
                ),
            ),
        }

        outcome = p5.orchestrate_workers(
            self.state(),
            self.signals(),
            [exploration_task, research_task],
            MockExecutor(results),
            citation_checker=StaticCitationChecker(),
        )

        self.assertEqual(outcome.source_conflicts, [["e1", "e2"]])
        self.assertFalse(outcome.synthesis_ready)


class CouncilBoundaryTests(unittest.TestCase):
    def test_council_disabled_keeps_perspective_label(self):
        decision = p5.council_gate(
            p5.CouncilConfig(requested=False), independent_agent_count=3
        )

        self.assertFalse(decision.enabled)
        self.assertEqual(decision.label, "PERSPECTIVE_LENSES")
        self.assertIsNone(decision.adapter_name)

    def test_requested_council_without_independent_agents_stays_disabled(self):
        decision = p5.council_gate(
            p5.CouncilConfig(requested=True, adapter_name="external-council"),
            independent_agent_count=1,
        )

        self.assertFalse(decision.enabled)
        self.assertEqual(decision.label, "PERSPECTIVE_LENSES")


if __name__ == "__main__":
    unittest.main()
