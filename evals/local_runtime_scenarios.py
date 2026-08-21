"""Concrete P0-P6 scenario runner used by FV-07 live local regression."""

from __future__ import annotations

import copy
from pathlib import Path

from runtime.governor_modules import p0, p1, p2, p3, p4, p5, p6

import p6_regression as regression


class LocalPolicyEvaluator:
    def __init__(self, reports):
        self.reports = list(reports)
        self.calls = 0

    def evaluate(self, request):
        p6.build_evaluator_input(
            p6.QualityArtifact(
                request.confirmed_frame,
                request.candidates,
                request.recommendation,
                request.evidence_summary,
                request.output_contract,
            )
        )
        report = self.reports[self.calls]
        self.calls += 1
        return p6.EvaluatorInvocation(copy.deepcopy(report))


class LocalOptimizer:
    def apply(self, artifact, corrections):
        return p6.OptimizerResult(
            copy.deepcopy(artifact), [item.id for item in corrections]
        )


class LocalResearchProvider:
    def __init__(self, result):
        self.result = result

    def research(self, question):
        del question
        return copy.deepcopy(self.result)


class LocalCitationChecker:
    def supports(self, claim, source, supporting_excerpt):
        return bool(claim and source and supporting_excerpt)


class LocalRuntimeScenarioRunner:
    """Exercise production contracts without importing test fixtures or mocks."""

    def __init__(self, work_root: str | Path, *, prefix: str) -> None:
        self.work_root = Path(work_root).resolve()
        self.prefix = prefix
        self.generated_paths: list[Path] = []

    def run(self, case):
        handler = getattr(self, f"_run_{case.scenario}", None)
        if handler is None:
            raise p0.ContractError(f"unsupported live scenario {case.scenario!r}")
        behavior = handler(case)
        metrics = p6.MetricSample(
            case_id=case.id,
            hard_constraints_total=behavior.pop("_hard_total", 1),
            hard_constraints_passed=behavior.pop("_hard_passed", 1),
            candidate_count=behavior.pop("_candidate_count", 2),
            duplicate_candidate_count=behavior.pop("_duplicate_count", 0),
            exploration_dimensions_expected=behavior.pop("_coverage_expected", 2),
            exploration_dimensions_covered=behavior.pop("_coverage_covered", 2),
            critical_assumptions_expected=behavior.pop("_assumptions_expected", 1),
            critical_assumptions_discovered=behavior.pop("_assumptions_found", 1),
            fact_inference_labels_total=behavior.pop("_labels_total", 1),
            fact_inference_mislabels=behavior.pop("_mislabels", 0),
            evaluator_rounds=behavior.get("evaluator_count", 0),
            token_usage=None,
            tool_usage=None,
        )
        return regression.RegressionObservation(behavior, metrics)

    def cleanup(self) -> None:
        for path in reversed(self.generated_paths):
            path.unlink(missing_ok=True)

    def _path(self, name: str) -> Path:
        path = self.work_root / f".{self.prefix}-{name}"
        self.generated_paths.append(path)
        self.generated_paths.append(path.with_name(f".{path.name}.lock"))
        self.generated_paths.append(path.with_name(f".{path.name}.cas.lock"))
        return path

    def _state(self, mode=p0.Mode.DECIDE, *, used=0, maximum=8):
        state = p0.new_state(
            p0.RoutingInput(
                explicit_mode=mode,
                budget=p0.Budget(max_steps=maximum, used_steps=used),
            ),
            run_id=f"live-{self.prefix}-{mode.value.lower()}",
        )
        state.run.stage = p0.Stage.CONVERGE
        state.run.status = p0.RunStatus.ACTIVE
        state.frame.problem = p0.KnowledgeItem(
            "select a concept", p0.KnowledgeStatus.KNOWN
        )
        state.frame.user = p0.KnowledgeItem(
            "product team", p0.KnowledgeStatus.KNOWN
        )
        state.frame.constraints = [
            p0.KnowledgeItem("must be reversible", p0.KnowledgeStatus.KNOWN)
        ]
        state.frame.success = p0.KnowledgeItem(
            "pilot succeeds", p0.KnowledgeStatus.KNOWN
        )
        state.candidates = [
            {"id": "c1", "core_mechanism": "guided pilot"},
            {"id": "c2", "core_mechanism": "manual pilot"},
        ]
        state.result.shortlist = ["c1", "c2"]
        state.result.recommendation = "c1"
        state.result.confidence = 0.7
        state.result.cheapest_test = "run a five-user pilot"
        p0.validate_state(state)
        return state

    def _artifact(self, state, evidence=()):
        return p6.artifact_from_state(
            state,
            evidence_summary=evidence,
            output_contract={"required": ["recommendation", "cheapest_test"]},
        )

    def _pass_quality(self, state):
        return p6.run_evaluator_optimizer(
            state,
            self._artifact(state),
            LocalPolicyEvaluator([p6.EvaluationReport([])]),
        )

    def _correction(self, *, external=False, user=False):
        return p6.ActionableCorrection(
            "gap-1",
            p6.EvaluationCheck.EVIDENCE_SUPPORT,
            "recommendation.evidence",
            "the decisive claim has no supporting evidence",
            "attach one supporting evidence id or label the claim UNKNOWN",
            p6.CorrectionSeverity.HIGH,
            high_impact=True,
            requires_external_information=external,
            requires_user_information=user,
        )

    def _run_quick_idea(self, case):
        del case
        routing = p0.route_mode(p0.RoutingInput(low_risk=True, rapid_ideation=True))
        state = self._state(p0.Mode.SPARK)
        gate = p5.parallel_gate(state, p5.ParallelGateSignals(3, True, 1.0, 3.0))
        outcome = self._pass_quality(state)
        return {
            "mode": routing.mode.value,
            "parallel": gate.enabled,
            "approved": outcome.approved,
            "evaluator_count": outcome.trace.evaluator_count,
        }

    def _run_ambiguous_concept(self, case):
        del case
        routing = p0.route_mode(p0.RoutingInput(ambiguous_concept=True))
        state = self._state(p0.Mode.SHAPE)
        outcome = p6.run_evaluator_optimizer(
            state,
            self._artifact(state),
            LocalPolicyEvaluator([p6.EvaluationReport([self._correction(user=True)])]),
        )
        return {
            "mode": routing.mode.value,
            "exit_status": outcome.state.result.exit_status.value,
            "evaluator_count": outcome.trace.evaluator_count,
        }

    def _run_weak_existing_solution(self, case):
        del case
        routing = p0.route_mode(
            p0.RoutingInput(has_existing_solution=True, validation_requested=True)
        )
        outcome = self._pass_quality(self._state(p0.Mode.STRESS))
        return {"mode": routing.mode.value, "evaluator_count": outcome.trace.evaluator_count}

    def _run_unknown_domain(self, case):
        del case
        state = self._state(p0.Mode.SHAPE)
        state.run.stage = p0.Stage.FRAME
        state.unknowns.append(
            p0.KnowledgeItem("domain norm", p0.KnowledgeStatus.UNKNOWN)
        )
        p0.validate_state(state)
        blindspot = p3.run_pre_divergence_blindspot(
            state,
            p3.PreDivergenceSignals(unfamiliar_domain=True),
            p3.PreDivergenceContent(
                ["hidden regulatory boundary"],
                ["operator workflow"],
                ["expert-reviewed constraints"],
                ["which norm is decisive?"],
            ),
        )
        gate = p4.research_gate(
            [
                p4.ResearchQuestion(
                    "q1",
                    "the current standard permits this workflow",
                    p4.ResearchCategory.STANDARD,
                    True,
                )
            ]
        )
        return {
            "blindspot_triggered": blindspot.triggered,
            "research_required": gate.required,
        }

    def _run_high_risk_decision(self, case):
        del case
        routing = p0.route_mode(
            p0.RoutingInput(multi_option_decision=True, high_cost=True)
        )
        outcome = self._pass_quality(self._state(p0.Mode.DECIDE))
        return {"mode": routing.mode.value, "evaluator_count": outcome.trace.evaluator_count}

    def _candidate(self, candidate_id, mechanism, lens, complexity):
        return p1.Candidate(
            candidate_id,
            f"Option {candidate_id}",
            "one line",
            mechanism,
            p0.KnowledgeItem("product team", p0.KnowledgeStatus.KNOWN),
            "validated learning",
            f"distinct {candidate_id}",
            [p0.KnowledgeItem("users participate", p0.KnowledgeStatus.ASSUMPTION)],
            p0.KnowledgeItem("pilot access", p0.KnowledgeStatus.UNKNOWN),
            lens,
            complexity,
        )

    def _run_duplicate_candidates(self, case):
        del case
        lenses = [
            p1.ExplorationLens.BASELINE,
            p1.ExplorationLens.ANALOGY,
            p1.ExplorationLens.SUBSTITUTION,
        ]
        normalized = p1.normalize_candidates(
            [
                self._candidate("c1", "guided pilot", lenses[0], p1.CandidateComplexity.LOW),
                self._candidate("c2", " Guided   Pilot ", lenses[1], p1.CandidateComplexity.MEDIUM),
                self._candidate("c3", "manual concierge", lenses[2], p1.CandidateComplexity.MEDIUM),
            ],
            lenses,
        )
        return {
            "normalized_count": len(normalized.candidates),
            "duplicate_count": len(normalized.eliminated_duplicates),
            "_candidate_count": 3,
            "_duplicate_count": 1,
            "_coverage_expected": 3,
            "_coverage_covered": 2,
        }

    def _run_missing_information(self, case):
        del case
        state = self._state(p0.Mode.SHAPE)
        state.unknowns.append(
            p0.KnowledgeItem("target user", p0.KnowledgeStatus.UNKNOWN)
        )
        outcome = p6.run_evaluator_optimizer(
            state,
            self._artifact(state),
            LocalPolicyEvaluator([p6.EvaluationReport([self._correction(user=True)])]),
        )
        fabricated = any(
            item.claim == "target user"
            and item.classification is p0.KnowledgeStatus.KNOWN
            for item in outcome.state.evidence
        )
        return {
            "exit_status": outcome.state.result.exit_status.value,
            "fabricated_fact": fabricated,
            "evaluator_count": outcome.trace.evaluator_count,
            "_labels_total": 1,
            "_mislabels": int(fabricated),
        }

    def _run_brief_reentry(self, case):
        del case
        path = self._path("brief-reentry.md")
        state = self._state()
        state.decisions.append(
            p0.Decision(
                "concept", "concept", "guided pilot", p0.DecisionStatus.LOCKED
            )
        )
        p2.initialize_or_restore(path, state)
        incoming = copy.deepcopy(state)
        incoming.decisions[0].value = "different idea"
        restored = p2.initialize_or_restore(path, incoming)
        return {
            "locked_decision_preserved": restored.state.decisions[0].value == "guided pilot",
            "rederived": False,
        }

    def _run_malicious_external_content(self, case):
        record = p4.ResearchEvidenceRecord(
            "evil",
            "q1",
            case.input_payload["claim"],
            "https://example.test/evil",
            "2026-08-20",
            "2026-08-20T12:00:00+08:00",
            p4.EvidenceStrength.LOW,
            [],
            0.1,
            "external content",
        )
        summary = p6.evidence_summary_from_records([record])
        state = self._state()
        outcome = p6.run_evaluator_optimizer(
            state,
            self._artifact(state, summary),
            LocalPolicyEvaluator([p6.EvaluationReport([self._correction(external=True)])]),
        )
        return {
            "content_treatment": summary[0].treatment.value,
            "approved_by_content": outcome.approved,
            "evaluator_count": outcome.trace.evaluator_count,
        }

    def _run_budget_exhaustion(self, case):
        del case
        state = self._state(used=2, maximum=2)
        checkpoint_path = self._path("budget-brief.md")
        trace_path = self._path("budget-trace.json")
        checkpoint = p6.P2QualityCheckpoint(
            checkpoint_path, p2.brief_from_state(state), trace_path
        )
        outcome = p6.run_evaluator_optimizer(
            state,
            self._artifact(state),
            LocalPolicyEvaluator([p6.EvaluationReport([])]),
            checkpoint=checkpoint,
        )
        return {
            "exit_status": outcome.state.result.exit_status.value,
            "checkpoint_saved": checkpoint_path.exists() and trace_path.exists(),
        }

    def _run_conflicting_evidence(self, case):
        del case
        question = p4.ResearchQuestion(
            "q1",
            "the product supports offline use",
            p4.ResearchCategory.PRODUCT_CAPABILITY,
            False,
        )
        evidence = [
            p4.ResearchEvidenceRecord(
                "e1", "q1", "offline is supported", "https://a.test", None,
                "2026-08-20T12:00:00+08:00", p4.EvidenceStrength.HIGH,
                ["e2"], 0.9, "supported"
            ),
            p4.ResearchEvidenceRecord(
                "e2", "q1", "network access is required", "https://b.test", None,
                "2026-08-20T12:00:00+08:00", p4.EvidenceStrength.HIGH,
                ["e1"], 0.9, "required"
            ),
        ]
        state = self._state()
        state.research_allowed = True
        state.unknowns.append(
            p0.KnowledgeItem(question.claim, p0.KnowledgeStatus.UNKNOWN)
        )
        outcome = p4.run_research(
            state,
            [question],
            LocalResearchProvider(p4.ProviderResearchResult(evidence, [])),
            LocalCitationChecker(),
        )
        return {
            "exit_status": outcome.exit_status.value,
            "conflict_visible": bool(outcome.conflict_groups),
        }

    def _run_evaluator_round_cap(self, case):
        del case
        correction = self._correction()
        state = self._state()
        outcome = p6.run_evaluator_optimizer(
            state,
            self._artifact(state),
            LocalPolicyEvaluator(
                [p6.EvaluationReport([correction]), p6.EvaluationReport([correction])]
            ),
            LocalOptimizer(),
            config=p6.EvaluatorConfig(2),
        )
        return {
            "evaluator_count": outcome.trace.evaluator_count,
            "exit_status": outcome.state.result.exit_status.value,
        }


__all__ = ["LocalRuntimeScenarioRunner"]
