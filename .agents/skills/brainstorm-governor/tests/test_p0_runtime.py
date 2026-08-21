from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "p0_runtime.py"
SPEC = importlib.util.spec_from_file_location("p0_runtime", SCRIPT_PATH)
assert SPEC and SPEC.loader
p0 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = p0
SPEC.loader.exec_module(p0)


class RouterTests(unittest.TestCase):
    def test_spark_route(self):
        result = p0.route_mode(p0.RoutingInput(low_risk=True, rapid_ideation=True))
        self.assertEqual(result.mode, p0.Mode.SPARK)

    def test_shape_route(self):
        result = p0.route_mode(p0.RoutingInput(ambiguous_concept=True))
        self.assertEqual(result.mode, p0.Mode.SHAPE)

    def test_stress_route(self):
        result = p0.route_mode(
            p0.RoutingInput(has_existing_solution=True, validation_requested=True)
        )
        self.assertEqual(result.mode, p0.Mode.STRESS)

    def test_decide_route(self):
        result = p0.route_mode(
            p0.RoutingInput(high_cost=True, multi_option_decision=True)
        )
        self.assertEqual(result.mode, p0.Mode.DECIDE)

    def test_explicit_mode_overrides_all_automatic_signals(self):
        result = p0.route_mode(
            p0.RoutingInput(
                explicit_mode=p0.Mode.SPARK,
                has_existing_solution=True,
                validation_requested=True,
                high_cost=True,
                multi_option_decision=True,
            )
        )
        self.assertEqual(result.mode, p0.Mode.SPARK)
        self.assertIn("explicit", result.routing_reason)

    def test_same_input_is_deterministic(self):
        request = p0.RoutingInput(
            low_reversibility=True,
            multi_option_decision=True,
            research_allowed=True,
        )
        first = p0.route_mode(request)
        second = p0.route_mode(request)
        self.assertEqual(first, second)

    def test_empty_boundary_input_defaults_to_shape(self):
        result = p0.route_mode(p0.RoutingInput())
        self.assertEqual(result.mode, p0.Mode.SHAPE)
        self.assertIn("insufficient", result.routing_reason)

    def test_automatic_upgrade_is_allowed(self):
        result = p0.route_mode(
            p0.RoutingInput(
                current_mode=p0.Mode.SPARK,
                ambiguous_concept=True,
            )
        )
        self.assertEqual(result.mode, p0.Mode.SHAPE)

    def test_automatic_downgrade_is_prevented(self):
        result = p0.route_mode(
            p0.RoutingInput(
                current_mode=p0.Mode.DECIDE,
                low_risk=True,
                rapid_ideation=True,
            )
        )
        self.assertEqual(result.mode, p0.Mode.DECIDE)
        self.assertIn("silently downgrade", result.routing_reason)

    def test_parallelism_respects_budget(self):
        with self.assertRaises(p0.StateValidationError):
            p0.route_mode(
                p0.RoutingInput(
                    requested_parallelism=2,
                    budget=p0.Budget(max_parallelism=1),
                )
            )


class StateValidationTests(unittest.TestCase):
    def make_state(self):
        return p0.new_state(p0.RoutingInput(), run_id="run-test")

    def test_new_state_contains_required_contract(self):
        state = self.make_state()
        payload = p0.state_to_dict(state)
        self.assertEqual(
            set(payload),
            {
                "run",
                "frame",
                "candidates",
                "assumptions",
                "unknowns",
                "evidence",
                "decisions",
                "deferred",
                "result",
                "routing_reason",
                "research_allowed",
                "parallelism",
            },
        )
        self.assertEqual(payload["run"]["mode"], "Shape")

    def test_round_trip_state_parser(self):
        state = self.make_state()
        restored = p0.state_from_dict(p0.state_to_dict(state))
        self.assertEqual(p0.state_to_dict(restored), p0.state_to_dict(state))

    def test_invalid_parallelism_is_rejected(self):
        state = self.make_state()
        state.parallelism = 0
        with self.assertRaises(p0.StateValidationError):
            p0.validate_state(state)

    def test_invalid_exit_status_is_rejected_by_parser(self):
        payload = p0.state_to_dict(self.make_state())
        payload["result"]["exit_status"] = "DONE"
        with self.assertRaises(p0.ContractError):
            p0.state_from_dict(payload)

    def test_terminal_state_requires_exit_status(self):
        state = self.make_state()
        state.run.status = p0.RunStatus.COMPLETED
        with self.assertRaises(p0.StateValidationError):
            p0.validate_state(state)

    def test_all_exit_statuses_are_valid_terminal_states(self):
        for exit_status in p0.ExitStatus:
            with self.subTest(exit_status=exit_status):
                state = self.make_state()
                state.run.status = p0.RunStatus.STOPPED
                state.result.exit_status = exit_status
                p0.validate_state(state)

    def test_unknown_list_cannot_contain_known_item(self):
        state = self.make_state()
        state.unknowns.append(
            p0.KnowledgeItem("target user", p0.KnowledgeStatus.KNOWN)
        )
        with self.assertRaises(p0.StateValidationError):
            p0.validate_state(state)

    def test_unknown_claim_cannot_also_be_known_evidence(self):
        state = self.make_state()
        state.unknowns.append(
            p0.KnowledgeItem("current market size", p0.KnowledgeStatus.UNKNOWN)
        )
        state.evidence.append(
            p0.EvidenceRecord(
                id="e-1",
                claim="Current market size",
                classification=p0.KnowledgeStatus.KNOWN,
                source="https://example.test/source",
            )
        )
        with self.assertRaises(p0.StateValidationError):
            p0.validate_state(state)

    def test_research_stage_requires_permission(self):
        state = self.make_state()
        state.run.stage = p0.Stage.RESEARCH
        with self.assertRaises(p0.StateValidationError):
            p0.validate_state(state)


class LockedDecisionTests(unittest.TestCase):
    def make_state_with_locked_decision(self):
        state = p0.new_state(p0.RoutingInput(), run_id="run-lock")
        state.decisions.append(
            p0.Decision(
                id="decision-1",
                topic="mode policy",
                value="single-agent default",
                status=p0.DecisionStatus.LOCKED,
                rationale="approved",
            )
        )
        p0.validate_state(state)
        return state

    def test_locked_decision_conflict_is_rejected(self):
        state = self.make_state_with_locked_decision()
        with self.assertRaises(p0.LockedDecisionConflict):
            p0.upsert_decision(
                state,
                p0.Decision(
                    id="decision-1",
                    topic="mode policy",
                    value="multi-agent default",
                    status=p0.DecisionStatus.LOCKED,
                    rationale="changed without log",
                ),
            )

    def test_identical_locked_decision_is_idempotent(self):
        state = self.make_state_with_locked_decision()
        existing = copy.deepcopy(state.decisions[0])
        updated = p0.upsert_decision(state, existing)
        self.assertEqual(p0.state_to_dict(updated), p0.state_to_dict(state))

    def test_open_decision_can_be_updated(self):
        state = p0.new_state(p0.RoutingInput(), run_id="run-open")
        state = p0.upsert_decision(
            state,
            p0.Decision(id="decision-1", topic="scope", value="A"),
        )
        state = p0.upsert_decision(
            state,
            p0.Decision(id="decision-1", topic="scope", value="B"),
        )
        self.assertEqual(state.decisions[0].value, "B")


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT_PATH), *args],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_route_cli(self):
        result = self.run_cli(
            "route",
            "--json",
            json.dumps({"ambiguous_concept": True}),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["mode"], "Shape")

    def test_validate_cli_rejects_invalid_state(self):
        state = p0.state_to_dict(
            p0.new_state(p0.RoutingInput(), run_id="run-cli")
        )
        state["run"]["mode"] = "invalid"
        result = self.run_cli("validate", "--json", json.dumps(state))
        self.assertEqual(result.returncode, 2)
        self.assertFalse(json.loads(result.stdout)["valid"])


if __name__ == "__main__":
    unittest.main()
