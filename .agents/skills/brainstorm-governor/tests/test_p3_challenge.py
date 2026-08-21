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
P3_PATH = SCRIPTS_DIR / "p3_challenge.py"
sys.path.insert(0, str(SCRIPTS_DIR))


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


p0 = load_module("p0_runtime", P0_PATH)
p3 = load_module("p3_challenge", P3_PATH)


class P3FixtureMixin:
    def state_at(self, stage, run_id="run-p3"):
        state = p0.new_state(
            p0.RoutingInput(explicit_mode=p0.Mode.SHAPE), run_id=run_id
        )
        state.run.stage = stage
        state.run.status = p0.RunStatus.ACTIVE
        state.frame.problem = p0.KnowledgeItem(
            "brainstorming misses critical failure modes", p0.KnowledgeStatus.KNOWN
        )
        state.frame.user = p0.KnowledgeItem(
            "independent product builder", p0.KnowledgeStatus.KNOWN
        )
        state.frame.success = p0.KnowledgeItem(
            "surface decisive risks before convergence", p0.KnowledgeStatus.KNOWN
        )
        state.frame.kill = p0.KnowledgeItem(
            "fatal dependency has no substitute", p0.KnowledgeStatus.KNOWN
        )
        p0.validate_state(state)
        return state

    def pre_content(self):
        return p3.PreDivergenceContent(
            landmines=["domain-specific approval may be mandatory"],
            hidden_context=["operators carry the exception-handling burden"],
            what_good_looks_like=["a domain expert can validate the workflow"],
            expert_questions=["which approval path is non-negotiable?"],
        )

    def blindspot_checks(self):
        checks = [
            p3.BlindspotCheck(category=item, finding=None)
            for item in p3.BlindspotCategory
        ]
        external_index = list(p3.BlindspotCategory).index(
            p3.BlindspotCategory.EXTERNAL_DEPENDENCIES
        )
        checks[external_index] = p3.BlindspotCheck(
            category=p3.BlindspotCategory.EXTERNAL_DEPENDENCIES,
            finding=p0.KnowledgeItem(
                "the only identity provider may be unavailable",
                p0.KnowledgeStatus.UNKNOWN,
            ),
        )
        return checks

    def assumptions(self, candidate_id="c1"):
        return [
            p3.AssumptionRecord(
                id="a-fatal",
                candidate_id=candidate_id,
                claim=p0.KnowledgeItem(
                    "users will migrate without incentives",
                    p0.KnowledgeStatus.ASSUMPTION,
                ),
                type=p3.AssumptionType.ADOPTION,
                importance=0.95,
                confidence=0.20,
                evidence=[],
                failure_impact=p3.FailureImpact.FATAL,
                cheapest_test="offer the migration flow to five target users",
            ),
            p3.AssumptionRecord(
                id="a-known",
                candidate_id=candidate_id,
                claim=p0.KnowledgeItem(
                    "the current operator reviews every exception",
                    p0.KnowledgeStatus.KNOWN,
                ),
                type=p3.AssumptionType.OPERATIONS,
                importance=0.70,
                confidence=0.90,
                evidence=["local:operator-workflow-note"],
                failure_impact=p3.FailureImpact.REPAIRABLE,
                cheapest_test="observe one exception review",
            ),
            p3.AssumptionRecord(
                id="a-unknown",
                candidate_id=candidate_id,
                claim=p0.KnowledgeItem(
                    "the substitute channel can reach target users",
                    p0.KnowledgeStatus.UNKNOWN,
                ),
                type=p3.AssumptionType.DISTRIBUTION,
                importance=0.60,
                confidence=0.10,
                evidence=[],
                failure_impact=p3.FailureImpact.REPAIRABLE,
                cheapest_test="run one channel smoke test",
            ),
        ]

    def pressure_tests(
        self,
        *,
        dependency_risk=p3.RiskClass.FATAL,
        steelman_first=True,
    ):
        tests = []
        for item in p3.PressureTestType:
            risk = p3.RiskClass.NONE
            related = []
            repair = None
            result = f"no material issue found in {item.value.lower()}"
            if item is p3.PressureTestType.DEPENDENCY_FAILURE:
                risk = dependency_risk
                related = ["a-fatal"]
                result = "identity-provider loss blocks the core workflow"
                if risk is p3.RiskClass.REPAIRABLE:
                    repair = "add a second identity provider"
            elif item is p3.PressureTestType.ADOPTION_FRICTION:
                risk = p3.RiskClass.REPAIRABLE
                related = ["a-fatal"]
                result = "manual migration creates first-week abandonment"
                repair = "provide assisted migration"
            elif item is p3.PressureTestType.STEELMAN:
                result = "the focused workflow removes repeated operator decisions"
            tests.append(
                p3.PressureTest(
                    type=item,
                    scenario=f"scenario for {item.value.lower()}",
                    result=result,
                    risk_class=risk,
                    related_assumption_ids=related,
                    repair_action=repair,
                )
            )
        steelman = next(
            item for item in tests if item.type is p3.PressureTestType.STEELMAN
        )
        tests.remove(steelman)
        if steelman_first:
            tests.insert(0, steelman)
        else:
            tests.append(steelman)
        return tests

    def challenge(self):
        return p3.CandidateChallengeInput(
            candidate_id="c1",
            blindspot_checks=self.blindspot_checks(),
            assumption_register=self.assumptions(),
            pressure_tests=self.pressure_tests(),
        )


class PreDivergenceTests(P3FixtureMixin, unittest.TestCase):
    def test_unfamiliar_domain_triggers_pre_blindspot(self):
        state = self.state_at(p0.Stage.FRAME)
        result = p3.run_pre_divergence_blindspot(
            state,
            p3.PreDivergenceSignals(unfamiliar_domain=True),
            self.pre_content(),
        )

        self.assertTrue(result.triggered)
        self.assertIn("unfamiliar_domain", result.trigger_reasons)
        self.assertTrue(result.landmines)
        self.assertTrue(result.expert_questions)

    def test_low_unknown_density_does_not_trigger(self):
        state = self.state_at(p0.Stage.FRAME)
        result = p3.run_pre_divergence_blindspot(
            state, p3.PreDivergenceSignals()
        )

        self.assertFalse(result.triggered)
        self.assertEqual(result.unknown_density, 0.0)
        self.assertEqual(result.landmines, [])

    def test_high_unknown_density_triggers(self):
        state = self.state_at(p0.Stage.FRAME)
        state.unknowns = [
            p0.KnowledgeItem("unknown regulation", p0.KnowledgeStatus.UNKNOWN),
            p0.KnowledgeItem("unknown operator", p0.KnowledgeStatus.UNKNOWN),
            p0.KnowledgeItem("unknown dependency", p0.KnowledgeStatus.UNKNOWN),
        ]
        p0.validate_state(state)
        result = p3.run_pre_divergence_blindspot(
            state, p3.PreDivergenceSignals(), self.pre_content()
        )

        self.assertTrue(result.triggered)
        self.assertIn("high_unknown_density", result.trigger_reasons)


class ChallengeEngineTests(P3FixtureMixin, unittest.TestCase):
    def test_high_importance_low_confidence_assumption_is_prioritized(self):
        state = self.state_at(p0.Stage.NORMALIZE)
        output = p3.run_challenge_engine(state, ["c1"], [self.challenge()])

        self.assertEqual(output.prioritized_assumption_ids, ["a-fatal"])
        self.assertIn("assumption:a-fatal", output.evidence_gaps)
        self.assertEqual(
            output.reports[0].knowledge_summary["KNOWN"], ["a-known"]
        )
        self.assertEqual(
            output.reports[0].knowledge_summary["ASSUMPTION"], ["a-fatal"]
        )
        self.assertEqual(
            output.reports[0].knowledge_summary["UNKNOWN"], ["a-unknown"]
        )

    def test_dependency_failure_surfaces_fatal_risk(self):
        output = p3.run_challenge_engine(
            self.state_at(p0.Stage.NORMALIZE), ["c1"], [self.challenge()]
        )

        dependency_risks = [
            item
            for item in output.fatal_risks
            if item.source == "pressure_test:DEPENDENCY_FAILURE"
        ]
        self.assertEqual(len(dependency_risks), 1)
        self.assertIn("blocks the core workflow", dependency_risks[0].statement)

    def test_fatal_and_repairable_risks_remain_separate(self):
        output = p3.run_challenge_engine(
            self.state_at(p0.Stage.NORMALIZE), ["c1"], [self.challenge()]
        )

        self.assertTrue(output.fatal_risks)
        self.assertTrue(output.repairable_risks)
        self.assertTrue(
            all(item.severity is p3.FailureImpact.FATAL for item in output.fatal_risks)
        )
        self.assertTrue(
            all(
                item.severity is p3.FailureImpact.REPAIRABLE
                for item in output.repairable_risks
            )
        )
        self.assertTrue(
            all(item.repair_action for item in output.repairable_risks)
        )

    def test_steelman_must_precede_fatal_classification(self):
        challenge = self.challenge()
        challenge = p3.CandidateChallengeInput(
            candidate_id=challenge.candidate_id,
            blindspot_checks=challenge.blindspot_checks,
            assumption_register=challenge.assumption_register,
            pressure_tests=self.pressure_tests(steelman_first=False),
        )

        with self.assertRaisesRegex(p0.ContractError, "STEELMAN"):
            p3.run_challenge_engine(
                self.state_at(p0.Stage.NORMALIZE), ["c1"], [challenge]
            )

    def test_blindspot_is_complete_and_does_not_eliminate(self):
        output = p3.run_challenge_engine(
            self.state_at(p0.Stage.NORMALIZE), ["c1"], [self.challenge()]
        )

        report = output.reports[0]
        self.assertEqual(len(report.blindspots), 1)
        self.assertEqual(
            report.blindspots[0].category,
            p3.BlindspotCategory.EXTERNAL_DEPENDENCIES,
        )
        self.assertFalse(hasattr(report, "eliminated"))
        self.assertIn("blindspot:EXTERNAL_DEPENDENCIES", report.evidence_gaps)

    def test_challenge_rejects_pre_normalize_stage_and_preserves_frame(self):
        with self.assertRaisesRegex(p0.ContractError, "before Divergence"):
            p3.run_challenge_engine(
                self.state_at(p0.Stage.DIVERGE), ["c1"], [self.challenge()]
            )

        state = self.state_at(p0.Stage.NORMALIZE)
        before = p0.state_to_dict(copy.deepcopy(state))["frame"]
        output = p3.run_challenge_engine(state, ["c1"], [self.challenge()])
        self.assertTrue(output.frame_unchanged)
        self.assertEqual(p0.state_to_dict(state)["frame"], before)

    def test_known_assumption_requires_evidence(self):
        assumptions = self.assumptions()
        assumptions[1] = p3.AssumptionRecord(
            id=assumptions[1].id,
            candidate_id=assumptions[1].candidate_id,
            claim=assumptions[1].claim,
            type=assumptions[1].type,
            importance=assumptions[1].importance,
            confidence=assumptions[1].confidence,
            evidence=[],
            failure_impact=assumptions[1].failure_impact,
            cheapest_test=assumptions[1].cheapest_test,
        )
        challenge = p3.CandidateChallengeInput(
            "c1", self.blindspot_checks(), assumptions, self.pressure_tests()
        )

        with self.assertRaisesRegex(p0.ContractError, "KNOWN claim requires evidence"):
            p3.run_challenge_engine(
                self.state_at(p0.Stage.NORMALIZE), ["c1"], [challenge]
            )

    def test_supported_assumption_types_are_complete(self):
        self.assertEqual(
            {item.value for item in p3.AssumptionType},
            {
                "DESIRABILITY",
                "FEASIBILITY",
                "VIABILITY",
                "ADOPTION",
                "DISTRIBUTION",
                "OPERATIONS",
                "TIMING",
            },
        )


class CliTests(P3FixtureMixin, unittest.TestCase):
    def test_pre_blindspot_cli(self):
        state = self.state_at(p0.Stage.FRAME)
        payload = {
            "state": p0.state_to_dict(state),
            "signals": p3._json_ready(
                p3.PreDivergenceSignals(explicit_requested=True)
            ),
            "content": p3._json_ready(self.pre_content()),
        }
        result = subprocess.run(
            [sys.executable, str(P3_PATH), "pre-blindspot"],
            input=json.dumps(payload),
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["triggered"])

    def test_challenge_cli(self):
        payload = {
            "state": p0.state_to_dict(self.state_at(p0.Stage.NORMALIZE)),
            "candidate_ids": ["c1"],
            "challenges": p3._json_ready([self.challenge()]),
            "high_importance_threshold": 0.70,
            "low_confidence_threshold": 0.40,
        }
        result = subprocess.run(
            [sys.executable, str(P3_PATH), "challenge"],
            input=json.dumps(payload),
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["prioritized_assumption_ids"], ["a-fatal"])
        self.assertTrue(output["fatal_risks"])


if __name__ == "__main__":
    unittest.main()
