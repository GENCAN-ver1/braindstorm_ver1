from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"
P0_PATH = SCRIPTS_DIR / "p0_runtime.py"
P2_PATH = SCRIPTS_DIR / "p2_persistence.py"
P4_PATH = SCRIPTS_DIR / "p4_research.py"
sys.path.insert(0, str(SCRIPTS_DIR))


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


p0 = load_module("p0_runtime", P0_PATH)
p2 = load_module("p2_persistence", P2_PATH)
p4 = load_module("p4_research", P4_PATH)


class StaticProvider:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def research(self, question):
        self.calls.append(question.id)
        if self.error is not None:
            raise self.error
        return self.result


class StaticCitationChecker:
    def __init__(self, supported=True):
        self.supported = supported

    def supports(self, claim, source, supporting_excerpt):
        return self.supported


class P4FixtureMixin:
    def make_state(self, *, research_allowed=True, claim=None):
        state = p0.new_state(
            p0.RoutingInput(research_allowed=research_allowed), run_id="run-p4"
        )
        state.run.stage = p0.Stage.CHALLENGE
        state.run.status = p0.RunStatus.ACTIVE
        if claim is not None:
            state.unknowns.append(
                p0.KnowledgeItem(claim, p0.KnowledgeStatus.UNKNOWN)
            )
        p0.validate_state(state)
        return state

    def question(
        self,
        *,
        question_id="q1",
        claim="The current product supports offline mode",
        category=p4.ResearchCategory.PRODUCT_CAPABILITY,
        time_sensitive=True,
        numeric_required=False,
    ):
        return p4.ResearchQuestion(
            id=question_id,
            claim=claim,
            category=category,
            time_sensitive=time_sensitive,
            numeric_required=numeric_required,
        )

    def evidence(
        self,
        *,
        evidence_id="e1",
        question_id="q1",
        claim="The current product supports offline mode",
        contradictions=None,
        numeric_claim_ids=None,
        source="https://docs.example.test/product",
    ):
        return p4.ResearchEvidenceRecord(
            id=evidence_id,
            question_id=question_id,
            claim=claim,
            source=source,
            source_date="2026-08-18",
            retrieved_at="2026-08-20T12:00:00+08:00",
            evidence_strength=p4.EvidenceStrength.HIGH,
            contradictions=[] if contradictions is None else contradictions,
            confidence=0.92,
            supporting_excerpt="Offline workflows are supported in the current release.",
            numeric_claim_ids=(
                [] if numeric_claim_ids is None else numeric_claim_ids
            ),
        )

    def run_research_fixture(self, question, result, *, checker=True, state=None):
        return p4.run_research(
            state or self.make_state(claim=question.claim),
            [question],
            StaticProvider(result=result),
            StaticCitationChecker(checker),
        )

    def temp_brief(self):
        path = SKILL_ROOT.parents[2] / f".{self._testMethodName}.P4_BRIEF.md"
        path.unlink(missing_ok=True)
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        return path


class ResearchGateTests(P4FixtureMixin, unittest.TestCase):
    def test_gate_only_triggers_defined_external_categories(self):
        external = self.question()
        local = self.question(
            question_id="q-local",
            claim="The team prefers a compact workflow",
            category=p4.ResearchCategory.LOCAL_OR_SUBJECTIVE,
            time_sensitive=False,
        )

        gate = p4.research_gate([external, local])

        self.assertTrue(gate.required)
        self.assertEqual(gate.required_question_ids, ["q1"])
        self.assertEqual(gate.skipped_question_ids, ["q-local"])

    def test_gate_cli(self):
        payload = {
            "questions": [p4._json_ready(self.question())],
            "existing_evidence": [],
            "existing_numeric_claims": [],
        }
        result = subprocess.run(
            [sys.executable, str(P4_PATH), "gate"],
            input=json.dumps(payload),
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["required_question_ids"], ["q1"])


class EvidenceValidationTests(P4FixtureMixin, unittest.TestCase):
    def test_valid_citation_is_persisted_as_summary_only(self):
        question = self.question()
        outcome = self.run_research_fixture(
            question,
            p4.ProviderResearchResult([self.evidence()], []),
        )

        self.assertIsNone(outcome.exit_status)
        self.assertEqual(outcome.unresolved_question_ids, [])
        self.assertEqual(outcome.state.run.stage, p0.Stage.RESEARCH)
        runtime_record = next(
            item for item in outcome.state.evidence if item.id == "p4:e1"
        )
        self.assertEqual(runtime_record.classification, p0.KnowledgeStatus.KNOWN)
        self.assertEqual(runtime_record.metadata["p4_kind"], "evidence_summary")
        self.assertNotIn("raw_results", json.dumps(p4._json_ready(outcome)))
        p4.validate_downstream_usage(outcome, evidence_ids=["e1"])

    def test_unsupported_citation_stops_without_persisting_fact(self):
        question = self.question()
        outcome = self.run_research_fixture(
            question,
            p4.ProviderResearchResult([self.evidence()], []),
            checker=False,
        )

        self.assertEqual(outcome.exit_status, p0.ExitStatus.RESEARCH_REQUIRED)
        self.assertEqual(outcome.unresolved_question_ids, ["q1"])
        self.assertEqual(outcome.evidence, [])
        self.assertFalse(any(item.id == "p4:e1" for item in outcome.state.evidence))
        self.assertIn("does not support claim", outcome.provider_failures[0])

    def test_conflicting_sources_are_not_silently_merged(self):
        question = self.question(time_sensitive=False)
        supporting = self.evidence(
            evidence_id="e-support",
            contradictions=["e-contradict"],
        )
        contradicting = self.evidence(
            evidence_id="e-contradict",
            claim="The current product requires a network connection",
            contradictions=["e-support"],
            source="https://status.example.test/limitations",
        )
        outcome = self.run_research_fixture(
            question,
            p4.ProviderResearchResult([supporting, contradicting], []),
        )

        self.assertEqual(outcome.exit_status, p0.ExitStatus.RESEARCH_REQUIRED)
        self.assertEqual(outcome.conflict_groups, [["e-contradict", "e-support"]])
        classifications = {
            item.id: item.classification
            for item in outcome.state.evidence
            if item.id.startswith("p4:e-")
        }
        self.assertEqual(
            set(classifications.values()), {p0.KnowledgeStatus.CONFLICT}
        )
        with self.assertRaisesRegex(p4.ResearchContractError, "conflicted evidence"):
            p4.validate_downstream_usage(outcome, evidence_ids=["e-support"])

    def test_numeric_value_inside_evidence_requires_numeric_claim(self):
        question = self.question(time_sensitive=False)
        naked = self.evidence(claim="The current price is 10 USD")

        with self.assertRaisesRegex(p4.ResearchContractError, "without NumericClaim"):
            p4.validate_provider_result(
                question,
                p4.ProviderResearchResult([naked], []),
                StaticCitationChecker(),
            )


class NumericStatusTests(P4FixtureMixin, unittest.TestCase):
    def test_estimate_requires_and_preserves_derivation_basis(self):
        question = self.question(
            claim="Projected first-month users",
            category=p4.ResearchCategory.GROWTH_DATA,
            time_sensitive=False,
            numeric_required=True,
        )
        estimate = p4.NumericClaim(
            id="n-estimate",
            question_id="q1",
            label="Projected first-month users",
            value=125,
            unit="users",
            status=p4.NumericStatus.ESTIMATE,
            estimate_basis="25 invited teams multiplied by 5 expected users",
        )
        outcome = self.run_research_fixture(
            question, p4.ProviderResearchResult([], [estimate])
        )

        self.assertIsNone(outcome.exit_status)
        runtime_record = next(
            item
            for item in outcome.state.evidence
            if item.id == "p4:numeric:n-estimate"
        )
        self.assertEqual(runtime_record.classification, p0.KnowledgeStatus.ASSUMPTION)
        self.assertEqual(
            runtime_record.metadata["estimate_basis"],
            "25 invited teams multiplied by 5 expected users",
        )

        invalid = p4.NumericClaim(
            id="n-invalid",
            question_id="q1",
            label="Projected first-month users",
            value=125,
            unit="users",
            status=p4.NumericStatus.ESTIMATE,
            estimate_basis=None,
        )
        with self.assertRaisesRegex(p4.ResearchContractError, "estimate_basis"):
            p4.validate_provider_result(
                question,
                p4.ProviderResearchResult([], [invalid]),
                StaticCitationChecker(),
            )

    def test_unknown_numeric_cannot_be_used_as_fact(self):
        question = self.question(
            claim="Current conversion rate",
            category=p4.ResearchCategory.BEHAVIOR_DATA,
            time_sensitive=False,
            numeric_required=True,
        )
        unknown = p4.NumericClaim(
            id="n-unknown",
            question_id="q1",
            label="Current conversion rate",
            value=None,
            unit="percent",
            status=p4.NumericStatus.UNKNOWN,
        )
        outcome = self.run_research_fixture(
            question, p4.ProviderResearchResult([], [unknown])
        )

        self.assertEqual(outcome.exit_status, p0.ExitStatus.RESEARCH_REQUIRED)
        with self.assertRaisesRegex(p4.ResearchContractError, "UNKNOWN numeric"):
            p4.validate_downstream_usage(
                outcome, numeric_claim_ids=["n-unknown"]
            )
        self.assertEqual(p4.downstream_view(outcome)["numeric_claims"], [])


class FailureAndPersistenceTests(P4FixtureMixin, unittest.TestCase):
    def test_provider_failure_safely_enters_research_required(self):
        question = self.question()
        provider = StaticProvider(error=p4.ResearchProviderError("provider unavailable"))

        outcome = p4.run_research(
            self.make_state(claim=question.claim),
            [question],
            provider,
            StaticCitationChecker(),
        )

        self.assertEqual(outcome.exit_status, p0.ExitStatus.RESEARCH_REQUIRED)
        self.assertEqual(outcome.state.run.status, p0.RunStatus.STOPPED)
        self.assertEqual(outcome.state.result.exit_status, p0.ExitStatus.RESEARCH_REQUIRED)
        self.assertEqual(outcome.evidence, [])
        self.assertIn("provider unavailable", outcome.provider_failures[0])

    def test_research_disabled_does_not_call_provider(self):
        question = self.question()
        provider = StaticProvider(
            result=p4.ProviderResearchResult([self.evidence()], [])
        )
        outcome = p4.run_research(
            self.make_state(research_allowed=False),
            [question],
            provider,
            StaticCitationChecker(),
        )

        self.assertEqual(provider.calls, [])
        self.assertEqual(outcome.exit_status, p0.ExitStatus.RESEARCH_REQUIRED)

    def test_p4_summary_round_trips_through_living_brief(self):
        question = self.question()
        outcome = self.run_research_fixture(
            question,
            p4.ProviderResearchResult([self.evidence()], []),
        )
        path = self.temp_brief()
        brief = p2.brief_from_state(outcome.state, next_action="continue convergence")

        p2.save_brief(path, brief)
        restored = p2.load_brief(path)

        record = next(item for item in restored.runtime_state.evidence if item.id == "p4:e1")
        self.assertEqual(record.metadata["p4_kind"], "evidence_summary")
        self.assertNotIn("raw_results", json.dumps(p2.brief_to_dict(restored)))


if __name__ == "__main__":
    unittest.main()
