from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"
P0_PATH = SCRIPTS_DIR / "p0_runtime.py"
P2_PATH = SCRIPTS_DIR / "p2_persistence.py"
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


class PersistenceTests(unittest.TestCase):
    def make_state(self, concept="guided workflow", run_id="run-p2"):
        state = p0.new_state(
            p0.RoutingInput(explicit_mode=p0.Mode.SHAPE),
            run_id=run_id,
        )
        state.frame.problem = p0.KnowledgeItem(
            "brainstorming loses durable context", p0.KnowledgeStatus.KNOWN
        )
        state.frame.user = p0.KnowledgeItem(
            "independent product builder", p0.KnowledgeStatus.KNOWN
        )
        state.frame.success = p0.KnowledgeItem(
            "resume without re-deriving decisions", p0.KnowledgeStatus.KNOWN
        )
        state.frame.kill = p0.KnowledgeItem(
            "restored state is inconsistent", p0.KnowledgeStatus.KNOWN
        )
        state.frame.constraints = [
            p0.KnowledgeItem(
                "no chat-history dependency", p0.KnowledgeStatus.KNOWN
            )
        ]
        state.assumptions = [
            p0.KnowledgeItem(
                "Markdown remains readable", p0.KnowledgeStatus.ASSUMPTION
            )
        ]
        state.unknowns = [
            p0.KnowledgeItem(
                "preferred resume action", p0.KnowledgeStatus.UNKNOWN
            )
        ]
        state.decisions = [
            p0.Decision(
                id="concept",
                topic="locked_concept",
                value=concept,
                status=p0.DecisionStatus.LOCKED,
                rationale="selected at Human Gate",
            )
        ]
        p0.validate_state(state)
        return state

    def temp_brief(self):
        path = SKILL_ROOT.parents[2] / f".{self._testMethodName}.CONCEPT_BRIEF.md"
        if path.exists():
            path.unlink()
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        return path

    def test_first_run_creates_complete_brief(self):
        path = self.temp_brief()
        result = p2.initialize_or_restore(
            path,
            self.make_state(),
            next_action="continue framing",
        )

        self.assertTrue(result.created)
        self.assertTrue(result.changed)
        self.assertTrue(path.exists())
        payload = p2.brief_to_dict(p2.load_brief(path))
        self.assertEqual(set(payload), p2.REQUIRED_BRIEF_KEYS)
        self.assertEqual(payload["current_stage"], "ROUTE")
        self.assertEqual(payload["status"], "READY")
        self.assertEqual(payload["next_action"], "continue framing")
        self.assertEqual(payload["open_questions"], ["preferred resume action"])
        self.assertEqual(
            payload["unvalidated_assumptions"], ["Markdown remains readable"]
        )

    def test_existing_brief_restores_persisted_state_first(self):
        path = self.temp_brief()
        state = self.make_state()
        p2.initialize_or_restore(path, state, next_action="continue framing")

        unrelated_new_session = self.make_state(run_id="new-session")
        unrelated_new_session.decisions = []
        result = p2.initialize_or_restore(path, unrelated_new_session)

        self.assertFalse(result.created)
        self.assertFalse(result.changed)
        self.assertEqual(result.state.run.id, "run-p2")
        self.assertEqual(result.state.decisions[0].value, "guided workflow")
        self.assertEqual(result.brief.next_action, "continue framing")
        self.assertEqual(result.conflicts, [])

    def test_locked_conflict_is_reported_without_overwrite(self):
        path = self.temp_brief()
        p2.initialize_or_restore(path, self.make_state("persisted concept"))

        result = p2.initialize_or_restore(path, self.make_state("incoming concept"))

        decision_conflicts = [
            item for item in result.conflicts if item.field == "decisions.concept.value"
        ]
        self.assertEqual(len(decision_conflicts), 1)
        self.assertEqual(result.state.decisions[0].value, "persisted concept")
        self.assertEqual(p2.load_brief(path).runtime_state.decisions[0].value, "persisted concept")

    def test_legal_locked_update_appends_traceable_log(self):
        path = self.temp_brief()
        result = p2.initialize_or_restore(path, self.make_state("old concept"))

        changed = p2.update_locked_decision(
            result.brief,
            "concept",
            "new concept",
            reason="pilot invalidated the old interaction model",
            evidence=["evidence:pilot-01"],
        )
        p2.save_brief(path, result.brief)
        restored = p2.load_brief(path)

        self.assertTrue(changed)
        self.assertEqual(restored.runtime_state.decisions[0].value, "new concept")
        self.assertEqual(len(restored.decision_log), 1)
        entry = restored.decision_log[0]
        self.assertEqual(entry.old_value, "old concept")
        self.assertEqual(entry.new_value, "new concept")
        self.assertEqual(entry.reason, "pilot invalidated the old interaction model")
        self.assertEqual(entry.evidence, ["evidence:pilot-01"])
        self.assertFalse(
            p2.update_locked_decision(
                restored,
                "concept",
                "new concept",
                reason="same value",
                evidence=["evidence:pilot-01"],
            )
        )
        self.assertEqual(len(restored.decision_log), 1)

    def test_locked_update_requires_reason_and_evidence(self):
        brief = p2.brief_from_state(self.make_state())
        with self.assertRaises(p0.ContractError):
            p2.update_locked_decision(
                brief, "concept", "new", reason="", evidence=["evidence:x"]
            )
        with self.assertRaises(p0.ContractError):
            p2.update_locked_decision(
                brief, "concept", "new", reason="valid reason", evidence=[]
            )

    def test_repeated_reentry_and_save_are_idempotent(self):
        path = self.temp_brief()
        first = p2.initialize_or_restore(path, self.make_state())
        first_bytes = path.read_bytes()

        second = p2.initialize_or_restore(path, self.make_state())
        changed = p2.save_brief(path, second.brief)

        self.assertFalse(second.created)
        self.assertFalse(second.changed)
        self.assertFalse(changed)
        self.assertEqual(path.read_bytes(), first_bytes)

    def test_round_save_persists_resume_point_and_elimination_reason(self):
        path = self.temp_brief()
        result = p2.initialize_or_restore(path, self.make_state())
        state = copy.deepcopy(result.state)
        state.run.stage = p0.Stage.FRAME
        state.run.status = p0.RunStatus.ACTIVE
        p0.validate_state(state)
        self.assertTrue(
            p2.record_elimination(
                result.brief,
                "c2",
                "Council workflow",
                "violates the single-agent boundary",
            )
        )

        p2.save_round(
            path,
            result.brief,
            state,
            next_action="run divergence",
            previous_stop_reason="waiting for frame confirmation",
        )
        restored = p2.load_brief(path)

        self.assertEqual(restored.runtime_state.run.stage, p0.Stage.FRAME)
        self.assertEqual(restored.runtime_state.run.status, p0.RunStatus.ACTIVE)
        self.assertEqual(restored.next_action, "run divergence")
        self.assertEqual(
            restored.previous_stop_reason, "waiting for frame confirmation"
        )
        self.assertEqual(restored.eliminated_candidates[0].candidate_id, "c2")
        self.assertEqual(
            restored.eliminated_candidates[0].reason,
            "violates the single-agent boundary",
        )

    def test_corrupt_and_missing_field_briefs_are_rejected(self):
        path = self.temp_brief()
        path.write_text(
            f"# CONCEPT_BRIEF\n\n{p2.START_MARKER}\n```json\n{{bad json\n```\n{p2.END_MARKER}\n",
            encoding="utf-8",
        )
        with self.assertRaises(p2.BriefValidationError):
            p2.load_brief(path)

        payload = p2.brief_to_dict(p2.brief_from_state(self.make_state()))
        del payload["problem"]
        with self.assertRaises(p2.BriefValidationError):
            p2.brief_from_dict(payload)

    def test_markdown_prose_is_not_used_as_recovery_state(self):
        path = self.temp_brief()
        p2.initialize_or_restore(path, self.make_state("canonical concept"))
        text = path.read_text(encoding="utf-8")
        path.write_text(
            text.replace(
                "## Locked concept\n\ncanonical concept",
                "## Locked concept\n\nprose-only edit",
            ),
            encoding="utf-8",
        )

        restored = p2.load_brief(path)
        self.assertEqual(restored.runtime_state.decisions[0].value, "canonical concept")


if __name__ == "__main__":
    unittest.main()
