from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"
P0_PATH = SCRIPTS_DIR / "p0_runtime.py"
P1_PATH = SCRIPTS_DIR / "p1_core.py"
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


def known(statement):
    return p0.KnowledgeItem(statement, p0.KnowledgeStatus.KNOWN)


def assumption(statement):
    return p0.KnowledgeItem(statement, p0.KnowledgeStatus.ASSUMPTION)


def unknown(statement):
    return p0.KnowledgeItem(statement, p0.KnowledgeStatus.UNKNOWN)


class P1FixtureMixin:
    def make_state(self, mode=p0.Mode.SHAPE, run_id="run-p1"):
        return p0.new_state(
            p0.RoutingInput(explicit_mode=mode),
            run_id=run_id,
        )

    def make_context(self, target_user=None):
        return p1.ContextIntake(
            requested_outcome=known("form a viable brainstorming workflow"),
            current_idea=assumption("structured stages improve idea quality"),
            target_user=target_user or known("independent product builder"),
            constraints=[known("must work without external research")],
            questions=[unknown("which mechanism users will prefer")],
            alternatives=[known("unstructured chat brainstorming")],
            assets=[],
        )

    def make_frame(self, target_user=None, hard_constraints=None):
        return p1.ProblemFrame(
            problem_statement=known("unstructured brainstorming loses decisions"),
            target_user=target_user or known("independent product builder"),
            job_to_be_done=known("turn a fuzzy idea into viable directions"),
            desired_change=known("produce testable directions without premature planning"),
            hard_constraints=(
                [known("must work without external research")]
                if hard_constraints is None
                else hard_constraints
            ),
            soft_preferences=[known("keep the workflow lightweight")],
            success_metric=known("at least two viable distinct directions"),
            kill_criterion=known("no candidate survives the hard constraints"),
            non_goals=[known("implementation planning")],
            time_horizon=known("one working session"),
        )

    def candidate(self, candidate_id, lens, complexity, mechanism):
        return p1.Candidate(
            id=candidate_id,
            title=f"Option {candidate_id}",
            one_liner=f"A distinct {candidate_id} direction",
            core_mechanism=mechanism,
            target_user=known("independent product builder"),
            value_created=f"Value from {candidate_id}",
            why_distinct=f"Distinct mechanism {candidate_id}",
            key_assumptions=[assumption(f"users accept {candidate_id}")],
            main_dependency=unknown(f"adoption evidence for {candidate_id}"),
            exploration_lens=lens,
            complexity=complexity,
        )

    def shape_candidates(self):
        return [
            self.candidate(
                "c1",
                p1.ExplorationLens.BASELINE,
                p1.CandidateComplexity.LOW,
                "guided interview workflow",
            ),
            self.candidate(
                "c2",
                p1.ExplorationLens.ANALOGY,
                p1.CandidateComplexity.MEDIUM,
                "design studio critique loop",
            ),
            self.candidate(
                "c3",
                p1.ExplorationLens.CONSTRAINT_REMOVAL,
                p1.CandidateComplexity.HIGH,
                "unbounded exploration canvas",
            ),
            self.candidate(
                "c4",
                p1.ExplorationLens.STAKEHOLDER_SHIFT,
                p1.CandidateComplexity.MEDIUM,
                "operator moderated workshop",
            ),
            self.candidate(
                "c5",
                p1.ExplorationLens.SUBSTITUTION,
                p1.CandidateComplexity.LOW,
                "replace product with reusable checklist",
            ),
        ]

    def challenges(self, candidates):
        return [
            p1.CandidateChallenge(
                candidate_id=item.id,
                blindspots=[f"migration friction for {item.id}"],
                assumption_audit=[assumption(f"users accept {item.id}")],
                pressure_test=[f"dependency failure for {item.id}"],
            )
            for item in candidates
        ]

    def assessments(self, candidates):
        values = {
            "c1": (0.90, 0.80, 0.70, 0.90, 0.20),
            "c2": (0.80, 0.70, 0.60, 0.80, 0.30),
            "c3": (0.95, 0.50, 0.40, 0.70, 0.40),
            "c4": (0.70, 0.90, 0.60, 0.60, 0.20),
            "c5": (0.75, 0.75, 0.80, 0.95, 0.15),
            "s1": (0.90, 0.90, 0.60, 0.90, 0.10),
            "s2": (0.95, 0.60, 0.50, 0.80, 0.30),
            "s3": (0.70, 0.95, 0.80, 1.00, 0.05),
        }
        return [
            p1.TradeoffAssessment(
                candidate_id=item.id,
                hard_constraint_violations=[],
                user_value=values[item.id][0],
                feasibility=values[item.id][1],
                evidence_confidence=values[item.id][2],
                reversibility=values[item.id][3],
                risk=values[item.id][4],
            )
            for item in candidates
        ]

    def make_request(self):
        candidates = self.shape_candidates()
        return p1.CoreLoopRequest(
            state=self.make_state(),
            context=self.make_context(),
            problem_frame=self.make_frame(),
            candidates=candidates,
            challenges=self.challenges(candidates),
            assessments=self.assessments(candidates),
            recommended_candidate_id="c1",
            confidence=0.82,
            cheapest_test="run five moderated sessions",
        )


class CoreLoopTests(P1FixtureMixin, unittest.TestCase):
    def test_complete_happy_path(self):
        output = p1.run_core_loop(self.make_request())

        self.assertEqual(
            output.stage_history,
            [
                p0.Stage.ROUTE,
                p0.Stage.CONTEXT,
                p0.Stage.FRAME,
                p0.Stage.DIVERGE,
                p0.Stage.NORMALIZE,
                p0.Stage.CHALLENGE,
                p0.Stage.CONVERGE,
                p0.Stage.STOPPED,
            ],
        )
        self.assertEqual(output.human_gate.recommendation, "c1")
        self.assertEqual(output.human_gate.exit_status, p0.ExitStatus.NEEDS_INPUT)
        self.assertEqual(output.state.run.status, p0.RunStatus.STOPPED)
        self.assertEqual(output.state.result.recommendation, "c1")
        self.assertTrue(output.human_gate.decisive_assumptions)
        self.assertTrue(output.human_gate.risks)

    def test_missing_critical_information_stops_safely(self):
        target = unknown("target user")
        request = p1.CoreLoopRequest(
            state=self.make_state(run_id="run-missing"),
            context=self.make_context(target_user=target),
            problem_frame=self.make_frame(target_user=target),
            candidates=[],
            challenges=[],
            assessments=[],
        )

        output = p1.run_core_loop(request)

        self.assertEqual(output.human_gate.exit_status, p0.ExitStatus.NEEDS_INPUT)
        self.assertIsNone(output.normalization)
        self.assertEqual(output.stage_history[-1], p0.Stage.STOPPED)
        self.assertIn("target user", [item.statement for item in output.state.unknowns])

    def test_all_candidates_violating_constraints_yields_iterate(self):
        request = self.make_request()
        request.recommended_candidate_id = None
        request.confidence = None
        request.cheapest_test = None
        for item in request.assessments:
            item.hard_constraint_violations = ["requires external research"]

        output = p1.run_core_loop(request)

        self.assertEqual(output.convergence.shortlist, [])
        self.assertEqual(output.human_gate.exit_status, p0.ExitStatus.ITERATE)
        self.assertEqual(
            set(output.convergence.eliminated_for_constraints),
            {item.id for item in request.candidates},
        )

    def test_no_single_winner_yields_explore(self):
        candidates = [self.shape_candidates()[0], self.shape_candidates()[4]]
        assessments = self.assessments(candidates)
        assessments[0].user_value = 0.95
        assessments[0].feasibility = 0.55
        assessments[0].evidence_confidence = 0.55
        assessments[0].reversibility = 0.70
        assessments[0].risk = 0.30
        assessments[1].user_value = 0.70
        assessments[1].feasibility = 0.95
        assessments[1].evidence_confidence = 0.85
        assessments[1].reversibility = 0.95
        assessments[1].risk = 0.10
        request = p1.CoreLoopRequest(
            state=self.make_state(run_id="run-tie"),
            context=self.make_context(),
            problem_frame=self.make_frame(),
            candidates=candidates,
            challenges=self.challenges(candidates),
            assessments=assessments,
        )

        output = p1.run_core_loop(request)

        self.assertEqual(len(output.convergence.shortlist), 2)
        self.assertIsNone(output.convergence.recommendation)
        self.assertEqual(output.human_gate.exit_status, p0.ExitStatus.EXPLORE)

    def test_hard_constraint_candidate_never_reaches_shortlist(self):
        request = self.make_request()
        request.recommended_candidate_id = "c5"
        request.assessments[0].hard_constraint_violations = [
            "requires external research"
        ]

        output = p1.run_core_loop(request)

        self.assertNotIn("c1", output.convergence.shortlist)
        self.assertEqual(output.convergence.recommendation, "c5")

    def test_challenge_does_not_modify_problem_frame(self):
        request = self.make_request()
        output = p1.run_core_loop(request)

        self.assertEqual(
            output.state.frame.problem,
            request.problem_frame.problem_statement,
        )
        self.assertEqual(
            output.state.frame.constraints,
            [
                *request.problem_frame.hard_constraints,
                *request.problem_frame.soft_preferences,
            ],
        )

    def test_assumptions_and_unknowns_remain_explicit(self):
        output = p1.run_core_loop(self.make_request())

        self.assertTrue(output.state.assumptions)
        self.assertTrue(output.state.unknowns)
        self.assertTrue(
            all(
                item.classification is p0.KnowledgeStatus.ASSUMPTION
                for item in output.state.assumptions
            )
        )
        self.assertTrue(
            all(
                item.classification is p0.KnowledgeStatus.UNKNOWN
                for item in output.state.unknowns
            )
        )


class DivergenceAndNormalizeTests(P1FixtureMixin, unittest.TestCase):
    def test_candidate_schema_rejects_score_or_rank(self):
        payload = p1._json_ready(self.shape_candidates()[0])
        payload["score"] = 0.9
        with self.assertRaises(p0.ContractError):
            p1.candidate_from_dict(payload)

    def test_duplicate_candidates_are_removed_by_mechanism(self):
        candidates = self.shape_candidates()
        duplicate = self.candidate(
            "c6",
            p1.ExplorationLens.SUBSTITUTION,
            p1.CandidateComplexity.LOW,
            "Guided interview workflow!!!",
        )
        result = p1.normalize_candidates(
            [*candidates, duplicate],
            p1.select_exploration_lenses(self.make_frame(), p0.Mode.SHAPE),
        )

        self.assertEqual(result.eliminated_duplicates["c6"], "duplicate core mechanism of c1")
        self.assertNotIn("c6", [item.id for item in result.candidates])

    def test_only_one_supplemental_divergence_round_is_allowed(self):
        with self.assertRaises(p0.ContractError):
            p1.normalize_candidates(
                self.shape_candidates(),
                p1.select_exploration_lenses(self.make_frame(), p0.Mode.SHAPE),
                supplemental_rounds=2,
            )

    def test_spark_uses_lightweight_three_lens_path(self):
        frame = self.make_frame(hard_constraints=[])
        candidates = [
            self.candidate(
                "s1",
                p1.ExplorationLens.BASELINE,
                p1.CandidateComplexity.LOW,
                "three prompt quick pass",
            ),
            self.candidate(
                "s2",
                p1.ExplorationLens.INVERSION,
                p1.CandidateComplexity.MEDIUM,
                "start from failure and reverse it",
            ),
            self.candidate(
                "s3",
                p1.ExplorationLens.SUBSTITUTION,
                p1.CandidateComplexity.LOW,
                "replace workshop with checklist",
            ),
        ]
        request = p1.CoreLoopRequest(
            state=self.make_state(mode=p0.Mode.SPARK, run_id="run-spark"),
            context=self.make_context(),
            problem_frame=frame,
            candidates=candidates,
            challenges=self.challenges(candidates),
            assessments=self.assessments(candidates),
            recommended_candidate_id="s1",
            confidence=0.70,
            cheapest_test="ask one user to choose among three directions",
        )

        output = p1.run_core_loop(request)

        self.assertEqual(
            output.selected_lenses,
            [
                p1.ExplorationLens.BASELINE,
                p1.ExplorationLens.INVERSION,
                p1.ExplorationLens.SUBSTITUTION,
            ],
        )
        self.assertEqual(output.human_gate.recommendation, "s1")


class ChallengeOrderingTests(P1FixtureMixin, unittest.TestCase):
    def test_challenge_cannot_run_before_divergence(self):
        candidate = self.shape_candidates()[0]
        state = self.make_state(run_id="run-order")
        with self.assertRaises(p0.ContractError):
            p1.validate_challenges(
                state,
                [candidate],
                self.challenges([candidate]),
            )


class CliTests(P1FixtureMixin, unittest.TestCase):
    def test_run_cli_happy_path(self):
        request = self.make_request()
        payload = {
            "state": p0.state_to_dict(request.state),
            "context": p1._json_ready(request.context),
            "problem_frame": p1._json_ready(request.problem_frame),
            "candidates": p1._json_ready(request.candidates),
            "challenges": p1._json_ready(request.challenges),
            "assessments": p1._json_ready(request.assessments),
            "recommended_candidate_id": request.recommended_candidate_id,
            "confidence": request.confidence,
            "cheapest_test": request.cheapest_test,
            "supplemental_candidates": [],
            "supplemental_rounds": 0,
        }
        result = subprocess.run(
            [sys.executable, str(P1_PATH), "run"],
            input=json.dumps(payload),
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["human_gate"]["recommendation"], "c1")
        self.assertEqual(output["state"]["result"]["exit_status"], "NEEDS_INPUT")


if __name__ == "__main__":
    unittest.main()
