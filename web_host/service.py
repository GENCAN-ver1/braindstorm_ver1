"""Typed application service joining browser sessions, P0/P1/P2/P6, and DeepSeek."""

from __future__ import annotations

import copy
import json
import threading
import uuid
from pathlib import Path
from typing import Any, Mapping, Protocol

from adapters.deepseek_p1 import DeepSeekGenerationResult, DeepSeekP1Adapter, DeepSeekProviderError
from adapters.openai_evaluator import (
    OpenAICompatibleEvaluatorConfig,
    OpenAICompatibleObservedEvaluatorAdapter,
    OpenAIEvaluatorError,
)
from runtime.governor_modules import p0, p1, p2, p6
from web_host.store import SessionStore, SessionStoreError


FRAME_KEYS = (
    "target_user",
    "core_task",
    "desired_change",
    "hard_constraints",
    "success_metrics",
    "abandonment_criteria",
    "non_goals",
    "validation_horizon",
)
LIST_FRAME_KEYS = {
    "hard_constraints",
    "success_metrics",
    "abandonment_criteria",
    "non_goals",
}
MODES = {"Shape", "Spark", "Stress", "Decide"}
STAGES = (
    ("route", "Route"),
    ("frame", "Frame"),
    ("diverge", "Diverge"),
    ("normalize", "Normalize"),
    ("challenge", "Challenge"),
    ("converge", "Converge"),
    ("capability", "External capabilities"),
    ("human-gate", "Human gate"),
    ("evaluator", "Evaluator"),
)
OUTPUT_CONTRACT = {
    "artifact_type": "brainstorm_web_handoff",
    "required": ["confirmed_frame", "candidates", "recommendation", "evidence_summary"],
}


class ServiceError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False, field: str | None = None):
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.field = field

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "code": self.code,
            "message": str(self),
            "retryable": self.retryable,
        }
        if self.field is not None:
            value["field"] = self.field
        return value


class Generator(Protocol):
    def generate(self, data_only_payload: Mapping[str, Any], *, operation_id: str) -> DeepSeekGenerationResult:
        ...


class Evaluator(Protocol):
    def evaluate(self, request: p6.EvaluatorInput) -> p6.EvaluatorInvocation:
        ...


class _OneShotEvaluator:
    def __init__(self, invocation: p6.EvaluatorInvocation) -> None:
        self.invocation = invocation

    def evaluate(self, _request: p6.EvaluatorInput) -> p6.EvaluatorInvocation:
        return copy.deepcopy(self.invocation)


class BrainstormService:
    def __init__(
        self,
        root: str | Path,
        *,
        generator: Generator | None = None,
        evaluator: Evaluator | None = None,
    ) -> None:
        self.store = SessionStore(root)
        self.generator = generator or DeepSeekP1Adapter()
        self.evaluator = evaluator
        self._provider_lock = threading.RLock()

    def create_session(self, request: Mapping[str, Any]) -> dict[str, Any]:
        idea = _bounded_text(request.get("idea"), "idea", maximum=8000)
        mode = request.get("mode")
        if mode not in MODES:
            raise ServiceError("VALIDATION_FAILURE", "Mode is invalid.", field="mode")
        frames = _validate_frames(request.get("frames"))
        session_id = f"session-{uuid.uuid4().hex}"
        session = {
            "schema_version": 1,
            "id": session_id,
            "revision": 0,
            "idea": idea,
            "mode": mode,
            "governorStatus": "NEEDS_INPUT",
            "frames": frames,
            "stages": _fresh_stages(),
            "phase": "created",
            "operations": {},
            "usage": [],
            "review": None,
            "handoff": None,
        }
        self.store.save(session)
        return _projection(session)

    def save_frames(self, session_id: str, revision: int, frames: Any) -> dict[str, Any]:
        session = self._load(session_id)
        self._require_revision(session, revision)
        session["frames"] = _validate_frames(frames)
        session["revision"] += 1
        session["phase"] = "created"
        session["governorStatus"] = "NEEDS_INPUT"
        session["review"] = None
        session["handoff"] = None
        self.store.save(session)
        return _projection(session)

    def start_run(self, session_id: str, revision: int) -> dict[str, Any]:
        with self._provider_lock:
            return self._start_run(session_id, revision)

    def _start_run(self, session_id: str, revision: int) -> dict[str, Any]:
        session = self._load(session_id)
        operation_id = f"start:{revision}"
        previous = session["operations"].get(operation_id)
        if previous == "complete":
            return _projection(session)
        if previous in {"in_flight", "failed"}:
            raise ServiceError(
                "PROVIDER_FAILURE",
                "The Provider operation for this revision cannot be replayed automatically; start a revised session.",
            )
        self._require_revision(session, revision)
        if session["phase"] in {"needs_input", "awaiting_human_gate", "committed"}:
            return _projection(session)
        if session["phase"] != "created":
            raise ServiceError("VALIDATION_FAILURE", "Session is not ready to run.")

        missing = _missing_frames(session["frames"])
        if missing:
            session["revision"] += 1
            session["phase"] = "needs_input"
            session["governorStatus"] = "NEEDS_INPUT"
            _set_stage(session, "route", "complete")
            _set_stage(session, "frame", "needs_input")
            session["operations"][operation_id] = "complete"
            self.store.save(session)
            return _projection(session)

        session["operations"][operation_id] = "in_flight"
        self.store.save(session)
        try:
            core_prefix, model_input = _build_model_input(session)
            generated = self.generator.generate(model_input, operation_id=f"{session_id}:{operation_id}")
            # A provider call is billable even when its generated payload later
            # fails the local Governor contract. Persist usage at the boundary so
            # the audit trail does not depend on schema acceptance.
            session["usage"].append(dict(generated.usage))
            core = {**core_prefix, **dict(generated.payload)}
            state = p0.new_state(
                p0.RoutingInput(
                    explicit_mode=p0.Mode(session["mode"]),
                    research_allowed=False,
                    requested_parallelism=1,
                    budget=p0.Budget(max_steps=64, max_parallelism=1),
                ),
                run_id=session_id,
            )
            core_request = p1.core_loop_request_from_dict({"state": p0.state_to_dict(state), **core})
            output = p1.run_core_loop(core_request)
            if output.human_gate.recommendation is None:
                raise p0.ContractError("model output did not produce a recommendation")
            brief = p2.brief_from_state(
                output.state,
                scope_in=["user-provided frame", "DeepSeek-generated P1 analysis"],
                scope_out=["external factual research", "multi-provider Council"],
                risks=list(output.human_gate.risks),
                next_action="review the recommendation at the Human Gate",
            )
            p2.save_brief(self.store.session_dir(session_id) / "living_brief.md", brief)
            session["revision"] += 1
            session["phase"] = "awaiting_human_gate"
            session["governorStatus"] = "ITERATE"
            session["governor_state"] = p0.state_to_dict(output.state)
            session["review"] = _review_from_output(output, generated.usage)
            for stage_id in ("route", "frame", "diverge", "normalize", "challenge", "converge"):
                _set_stage(session, stage_id, "complete")
            _set_stage(session, "capability", "skipped")
            _set_stage(session, "human-gate", "pending")
            session["operations"][operation_id] = "complete"
            self.store.save(session)
            return _projection(session)
        except DeepSeekProviderError as exc:
            if exc.usage is not None:
                session["usage"].append(dict(exc.usage))
            session["operations"][operation_id] = "failed"
            self.store.save(session)
            raise ServiceError("PROVIDER_FAILURE", str(exc), retryable=False) from None
        except OpenAIEvaluatorError as exc:
            session["operations"][operation_id] = "failed"
            self.store.save(session)
            raise ServiceError("PROVIDER_FAILURE", str(exc), retryable=False) from None
        except (p0.ContractError, TypeError, ValueError, KeyError, json.JSONDecodeError):
            session["operations"].pop(operation_id, None)
            self.store.save(session)
            raise ServiceError(
                "PROVIDER_FAILURE",
                "DeepSeek returned an invalid governed response.",
                retryable=True,
            ) from None

    def resume_run(self, session_id: str, revision: int, submission: Mapping[str, Any]) -> dict[str, Any]:
        session = self._load(session_id)
        self._require_revision(session, revision)
        if session["phase"] != "needs_input":
            raise ServiceError("VALIDATION_FAILURE", "Session is not waiting for input.")
        _apply_submission(session, submission)
        session["revision"] += 1
        if _missing_frames(session["frames"]):
            session["governorStatus"] = "NEEDS_INPUT"
        else:
            session["phase"] = "created"
            session["governorStatus"] = "EXPLORE"
            _set_stage(session, "frame", "complete")
        self.store.save(session)
        return _projection(session)

    def configure_capabilities(self, session_id: str, revision: int, request: Mapping[str, Any]) -> dict[str, Any]:
        session = self._load(session_id)
        self._require_revision(session, revision)
        if request.get("outcome") != "skip":
            raise ServiceError(
                "VALIDATION_FAILURE",
                "Real multi-provider Council is outside this DeepSeek host scope.",
            )
        session["revision"] += 1
        self.store.save(session)
        return _projection(session)

    def submit_human_gate(self, session_id: str, revision: int, decision: Mapping[str, Any]) -> dict[str, Any]:
        with self._provider_lock:
            return self._submit_human_gate(session_id, revision, decision)

    def _submit_human_gate(self, session_id: str, revision: int, decision: Mapping[str, Any]) -> dict[str, Any]:
        session = self._load(session_id)
        operation_id = f"human-gate:{revision}"
        if session["operations"].get(operation_id) == "complete":
            return _projection(session)
        if session["operations"].get(operation_id) in {"in_flight", "failed"}:
            raise ServiceError(
                "PROVIDER_FAILURE",
                "The Evaluator operation for this revision cannot be replayed automatically; start a revised session.",
            )
        self._require_revision(session, revision)
        if session["phase"] != "awaiting_human_gate":
            raise ServiceError("VALIDATION_FAILURE", "Session is not awaiting Human Gate review.")
        kind = decision.get("kind")
        if kind == "request_iteration":
            _bounded_text(decision.get("feedback"), "feedback", maximum=4000)
            session["revision"] += 1
            session["governorStatus"] = "ITERATE"
            _set_stage(session, "human-gate", "needs_input")
            self.store.save(session)
            return _projection(session)
        if kind == "provide_missing_input":
            _apply_submission(session, decision.get("input"))
            session["revision"] += 1
            session["phase"] = "created"
            session["governorStatus"] = "NEEDS_INPUT"
            session["review"] = None
            session["handoff"] = None
            self.store.save(session)
            return _projection(session)
        if kind != "confirm":
            raise ServiceError("VALIDATION_FAILURE", "Human Gate decision is invalid.")

        session["operations"][operation_id] = "in_flight"
        self.store.save(session)
        try:
            state = p0.state_from_dict(session["governor_state"])
            state.run.status = p0.RunStatus.ACTIVE
            state.result.exit_status = None
            state.decisions.append(
                p0.Decision(
                    id=f"human-gate-{session_id}",
                    topic="concept",
                    value=state.result.recommendation,
                    status=p0.DecisionStatus.LOCKED,
                    rationale="The user explicitly confirmed this recommendation in the web Human Gate.",
                )
            )
            p0.validate_state(state)
            artifact = p6.artifact_from_state(state, output_contract=OUTPUT_CONTRACT)
            evaluator, usage = self._bounded_evaluator(artifact)
            outcome = p6.run_evaluator_optimizer(
                state,
                artifact,
                evaluator,
                optimizer=None,
                config=p6.EvaluatorConfig(evaluator_rounds=1),
            )
            if usage is not None:
                session["usage"].append(usage)
            session["revision"] += 1
            session["governor_state"] = p0.state_to_dict(outcome.state)
            if outcome.approved:
                artifact_path = self.store.session_dir(session_id) / "approved_artifact.json"
                artifact_path.write_text(
                    json.dumps(p6._json_ready(outcome.artifact), ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                handoff = p6.build_final_handoff(
                    outcome,
                    approved_artifact_path=artifact_path.resolve(),
                    acceptance_criteria=[session["frames"]["success_metrics"]["value"][0]],
                    risks=(session.get("review") or {}).get("risks", []),
                    next_validation=(session.get("review") or {}).get("cheapestTest") or "Run the cheapest validation test.",
                )
                session["handoff"] = _browser_handoff(session, handoff)
                session["phase"] = "committed"
                session["governorStatus"] = "COMMIT"
                _set_stage(session, "human-gate", "complete")
                _set_stage(session, "evaluator", "complete")
            else:
                session["governorStatus"] = outcome.state.result.exit_status.value
                _set_stage(session, "human-gate", "needs_input")
                _set_stage(session, "evaluator", "complete")
                if session.get("review") is not None:
                    session["review"]["corrections"] = [p6._json_ready(item) for item in outcome.remaining_corrections]
            brief_path = self.store.session_dir(session_id) / "living_brief.md"
            brief = p2.load_brief(brief_path)
            p2.save_round(
                brief_path,
                brief,
                outcome.state,
                next_action=("render the final handoff" if outcome.approved else "address evaluator corrections"),
                previous_stop_reason=outcome.stop_reason.value,
            )
            session["operations"][operation_id] = "complete"
            self.store.save(session)
            return _projection(session)
        except (DeepSeekProviderError, OpenAIEvaluatorError) as exc:
            session["operations"][operation_id] = "failed"
            self.store.save(session)
            raise ServiceError("PROVIDER_FAILURE", str(exc), retryable=False) from None
        except p0.ContractError:
            session["operations"].pop(operation_id, None)
            self.store.save(session)
            raise ServiceError("PROVIDER_FAILURE", "Evaluator returned an invalid governed response.", retryable=True) from None

    def get_handoff(self, session_id: str) -> dict[str, Any] | None:
        session = self._load(session_id)
        return copy.deepcopy(session["handoff"]) if session["governorStatus"] == "COMMIT" else None

    def get_session(self, session_id: str) -> dict[str, Any]:
        return _projection(self._load(session_id))

    def _bounded_evaluator(self, artifact: p6.QualityArtifact) -> tuple[Evaluator, dict[str, Any] | None]:
        if self.evaluator is not None:
            return self.evaluator, None
        observed = OpenAICompatibleObservedEvaluatorAdapter(
            OpenAICompatibleEvaluatorConfig(
                base_url="https://api.deepseek.com",
                model="deepseek-v4-pro",
                credential_env="DEEPSEEK_API_KEY",
                timeout_seconds=60,
                max_output_tokens=4096,
                provider_options={"thinking": {"type": "disabled"}},
            )
        ).evaluate(p6.build_evaluator_input(artifact))
        provider_usage = observed.usage
        usage = {
            "provider": "deepseek",
            "model": "deepseek-v4-pro",
            "request_id": provider_usage.request_id,
            "prompt_tokens": provider_usage.prompt_tokens,
            "completion_tokens": provider_usage.completion_tokens,
            "total_tokens": None if provider_usage.prompt_tokens is None or provider_usage.completion_tokens is None else provider_usage.prompt_tokens + provider_usage.completion_tokens,
            "latency_ms": provider_usage.latency_ms,
        }
        return _OneShotEvaluator(observed.payload), usage

    def _load(self, session_id: str) -> dict[str, Any]:
        try:
            return self.store.load(session_id)
        except SessionStoreError as exc:
            raise ServiceError("VALIDATION_FAILURE", str(exc)) from None

    @staticmethod
    def _require_revision(session: Mapping[str, Any], revision: int) -> None:
        if type(revision) is not int or session["revision"] != revision:
            raise ServiceError("REVISION_CONFLICT", "Session revision is stale.", retryable=True)


def _build_model_input(session: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    frames = session["frames"]
    known = lambda statement, classification="KNOWN": {"statement": statement, "classification": classification}
    list_items = lambda key: [known(value, frames[key]["status"]) for value in frames[key]["value"]]
    context = {
        "requested_outcome": known(frames["desired_change"]["value"], frames["desired_change"]["status"]),
        "current_idea": known(session["idea"]),
        "target_user": known(frames["target_user"]["value"], frames["target_user"]["status"]),
        "constraints": list_items("hard_constraints"),
        "questions": [],
        "alternatives": [],
        "assets": [],
    }
    problem_frame = {
        "problem_statement": known(session["idea"]),
        "target_user": copy.deepcopy(context["target_user"]),
        "job_to_be_done": known(frames["core_task"]["value"], frames["core_task"]["status"]),
        "desired_change": copy.deepcopy(context["requested_outcome"]),
        "hard_constraints": list_items("hard_constraints"),
        "soft_preferences": [],
        "success_metric": known("; ".join(frames["success_metrics"]["value"]), frames["success_metrics"]["status"]),
        "kill_criterion": known("; ".join(frames["abandonment_criteria"]["value"]), frames["abandonment_criteria"]["status"]),
        "non_goals": list_items("non_goals"),
        "time_horizon": known(frames["validation_horizon"]["value"], frames["validation_horizon"]["status"]),
    }
    temporary_state = p0.new_state(
        p0.RoutingInput(explicit_mode=p0.Mode(session["mode"]), budget=p0.Budget(max_steps=64)),
        run_id=session["id"],
    )
    typed_frame = p1.core_loop_request_from_dict(
        {
            "state": p0.state_to_dict(temporary_state),
            "context": context,
            "problem_frame": problem_frame,
            "candidates": [_placeholder_candidate(problem_frame, "BASELINE")],
            "challenges": [{"candidate_id": "placeholder", "blindspots": ["placeholder"], "assumption_audit": [known("placeholder", "ASSUMPTION")], "pressure_test": ["placeholder"]}],
            "assessments": [{"candidate_id": "placeholder", "hard_constraint_violations": [], "user_value": 1, "feasibility": 1, "evidence_confidence": 1, "reversibility": 1, "risk": 1}],
            "recommended_candidate_id": "placeholder",
            "confidence": 0.5,
            "cheapest_test": "placeholder",
            "supplemental_candidates": [],
            "supplemental_rounds": 0,
        }
    ).problem_frame
    lenses = [item.value for item in p1.select_exploration_lenses(typed_frame, p0.Mode(session["mode"]))]
    return (
        {"context": context, "problem_frame": problem_frame, "supplemental_candidates": [], "supplemental_rounds": 0},
        {
            "idea": session["idea"],
            "mode": session["mode"],
            "confirmed_frame": problem_frame,
            "allowed_lenses": lenses,
            "output_contract": {
                "exact_keys": ["candidates", "challenges", "assessments", "recommended_candidate_id", "confidence", "cheapest_test"],
                "candidate_count": f"3 to {len(lenses)}; use only allowed_lenses, include LOW complexity and INVERSION or SUBSTITUTION",
                "knowledge_item": {"statement": "non-empty string", "classification": "ASSUMPTION or UNKNOWN for generated claims"},
                "candidate_exact_keys": ["id", "title", "one_liner", "core_mechanism", "target_user", "value_created", "why_distinct", "key_assumptions", "main_dependency", "exploration_lens", "complexity"],
                "candidate_rules": "unique ids and core_mechanisms; target_user/main_dependency are knowledge_item objects; key_assumptions is a non-empty knowledge_item array; complexity is LOW, MEDIUM, or HIGH",
                "challenge_exact_keys": ["candidate_id", "blindspots", "assumption_audit", "pressure_test"],
                "challenge_rules": "blindspots and pressure_test are non-empty string arrays; assumption_audit is a non-empty knowledge_item array",
                "assessment_exact_keys": ["candidate_id", "hard_constraint_violations", "user_value", "feasibility", "evidence_confidence", "reversibility", "risk"],
                "scores": "finite numbers from 0 through 1",
                "challenge_and_assessment": "exactly one for every candidate id",
                "recommendation": "must survive hard constraints and Pareto dominance",
            },
        },
    )


def _placeholder_candidate(problem_frame: Mapping[str, Any], lens: str) -> dict[str, Any]:
    return {
        "id": "placeholder", "title": "placeholder", "one_liner": "placeholder",
        "core_mechanism": "placeholder", "target_user": problem_frame["target_user"],
        "value_created": "placeholder", "why_distinct": "placeholder",
        "key_assumptions": [{"statement": "placeholder", "classification": "ASSUMPTION"}],
        "main_dependency": {"statement": "placeholder", "classification": "ASSUMPTION"},
        "exploration_lens": lens, "complexity": "LOW",
    }


def _review_from_output(output: p1.CoreLoopOutput, usage: Mapping[str, Any]) -> dict[str, Any]:
    candidates = [] if output.normalization is None else [
        {
            "id": item.id,
            "title": item.title,
            "oneLiner": item.one_liner,
            "coreMechanism": item.core_mechanism,
            "valueCreated": item.value_created,
            "whyDistinct": item.why_distinct,
            "lens": item.exploration_lens.value,
            "complexity": item.complexity.value,
        }
        for item in output.normalization.candidates
    ]
    return {
        "provider": "DeepSeek",
        "model": "deepseek-v4-pro",
        "candidates": candidates,
        "recommendation": output.human_gate.recommendation,
        "confidence": output.state.result.confidence,
        "cheapestTest": output.human_gate.cheapest_test,
        "risks": list(output.human_gate.risks),
        "usage": dict(usage),
        "corrections": [],
    }


def _browser_handoff(session: Mapping[str, Any], handoff: p6.FinalHandoff) -> dict[str, Any]:
    frames = session["frames"]
    lines = [f"{key}: {frames[key]['value']}" for key in FRAME_KEYS]
    return {
        "problem_frame": "\n".join(lines),
        "locked_decisions": [f"{item['topic']}: {item['value']}" for item in handoff.locked_decisions],
        "open_questions": list(handoff.open_questions),
        "non_goals": list(handoff.non_goals),
        "acceptance_criteria": list(handoff.acceptance_criteria),
        "evidence_summary": ["P1 generation and P6 evaluation used DeepSeek deepseek-v4-pro; no external factual research was claimed."],
        "recommended_next_action": handoff.next_validation,
    }


def _validate_frames(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != set(FRAME_KEYS):
        raise ServiceError("VALIDATION_FAILURE", "Frame schema is invalid.")
    result = {}
    for key in FRAME_KEYS:
        item = value[key]
        if not isinstance(item, Mapping) or set(item) != {"value", "status", "source"}:
            raise ServiceError("VALIDATION_FAILURE", f"Frame {key} is invalid.", field=key)
        status = item["status"]
        if status not in {"UNKNOWN", "ASSUMPTION", "KNOWN", "CONFLICT"}:
            raise ServiceError("VALIDATION_FAILURE", f"Frame {key} status is invalid.", field=key)
        if item["source"] not in {"user", "ai"}:
            raise ServiceError("VALIDATION_FAILURE", f"Frame {key} source is invalid.", field=key)
        if key in LIST_FRAME_KEYS:
            raw = item["value"]
            if not isinstance(raw, list) or len(raw) > 20:
                raise ServiceError("VALIDATION_FAILURE", f"Frame {key} must be a bounded list.", field=key)
            cleaned = [_bounded_text(entry, key, maximum=2000, allow_blank=True) for entry in raw]
        else:
            cleaned = _bounded_text(item["value"], key, maximum=4000, allow_blank=True)
        result[key] = {"value": cleaned, "status": status, "source": item["source"]}
    return result


def _bounded_text(value: Any, field: str, *, maximum: int, allow_blank: bool = False) -> str:
    if not isinstance(value, str) or len(value) > maximum or (not allow_blank and not value.strip()):
        raise ServiceError("VALIDATION_FAILURE", f"{field} is invalid.", field=field)
    return value.strip()


def _missing_frames(frames: Mapping[str, Any]) -> list[str]:
    missing = []
    for key in FRAME_KEYS:
        item = frames[key]
        value = item["value"]
        blank = not value or (isinstance(value, list) and not any(entry.strip() for entry in value)) or (isinstance(value, str) and not value.strip())
        if item["status"] in {"UNKNOWN", "CONFLICT"} or blank:
            missing.append(key)
    return missing


def _apply_submission(session: dict[str, Any], submission: Any) -> None:
    if not isinstance(submission, Mapping):
        raise ServiceError("VALIDATION_FAILURE", "Missing-input submission is invalid.")
    field = submission.get("field")
    if field not in FRAME_KEYS:
        raise ServiceError("VALIDATION_FAILURE", "Missing-input field is invalid.")
    frames = copy.deepcopy(session["frames"])
    item = copy.deepcopy(frames[field])
    item["value"] = submission.get("value")
    item["status"] = submission.get("status")
    item["source"] = "user"
    frames[field] = item
    session["frames"] = _validate_frames(frames)


def _fresh_stages() -> list[dict[str, str]]:
    return [{"id": stage_id, "label": label, "status": "pending"} for stage_id, label in STAGES]


def _set_stage(session: dict[str, Any], stage_id: str, status: str) -> None:
    for stage in session["stages"]:
        if stage["id"] == stage_id:
            stage["status"] = status
            return


def _projection(session: Mapping[str, Any]) -> dict[str, Any]:
    return copy.deepcopy({
        "id": session["id"],
        "revision": session["revision"],
        "mode": session["mode"],
        "governorStatus": session["governorStatus"],
        "frames": session["frames"],
        "stages": session["stages"],
        "review": session.get("review"),
    })


__all__ = ["BrainstormService", "ServiceError"]
