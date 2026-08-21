from __future__ import annotations

import copy

from runtime.governor_modules import p0, p1, p4, p5


class StaticCitationChecker:
    def __init__(self, supported=True):
        self.supported = supported

    def supports(self, claim, source, supporting_excerpt):
        return self.supported


class ResearchProvider:
    def __init__(self, results):
        self.results = results
        self.calls = []

    def research(self, question):
        self.calls.append(question.id)
        result = self.results[question.id]
        if isinstance(result, BaseException):
            raise result
        return copy.deepcopy(result)


class MockExecutor:
    def __init__(self, results):
        self.results = results
        self.open_calls = 0
        self.submitted = []
        self.collected = []

    def open(self, max_parallelism):
        self.open_calls += 1
        self.max_parallelism = max_parallelism

    def submit(self, task):
        self.submitted.append(copy.deepcopy(task))
        return f"handle:{task.id}"

    def collect(self, handle):
        worker_id = handle.split("handle:", 1)[1]
        self.collected.append(worker_id)
        result = self.results[worker_id]
        if isinstance(result, BaseException):
            raise result
        return copy.deepcopy(result)


def state(run_id="run-fv04", *, parallelism=3, research_allowed=True):
    value = p0.new_state(
        p0.RoutingInput(
            explicit_mode=p0.Mode.DECIDE,
            research_allowed=research_allowed,
            requested_parallelism=parallelism,
            budget=p0.Budget(max_steps=64, max_parallelism=parallelism),
        ),
        run_id=run_id,
    )
    value.frame.problem = p0.KnowledgeItem(
        "find isolated solution mechanisms", p0.KnowledgeStatus.KNOWN
    )
    value.frame.user = p0.KnowledgeItem(
        "product team", p0.KnowledgeStatus.KNOWN
    )
    value.frame.constraints = [
        p0.KnowledgeItem("must remain reversible", p0.KnowledgeStatus.KNOWN)
    ]
    value.decisions = [
        p0.Decision(
            id="locked-scope",
            topic="scope",
            value="concept only",
            status=p0.DecisionStatus.LOCKED,
            rationale="acceptance invariant",
        )
    ]
    value.evidence = [
        p0.EvidenceRecord(
            id="existing-evidence",
            claim="existing validated fact",
            classification=p0.KnowledgeStatus.KNOWN,
            source="fixture",
        )
    ]
    p0.validate_state(value)
    return value


def question(question_id):
    return p4.ResearchQuestion(
        id=question_id,
        claim=f"Current capability claim {question_id}",
        category=p4.ResearchCategory.PRODUCT_CAPABILITY,
        time_sensitive=True,
    )


def evidence(question_id, evidence_id=None):
    evidence_id = evidence_id or f"e-{question_id}"
    return p4.ResearchEvidenceRecord(
        id=evidence_id,
        question_id=question_id,
        claim=f"Current capability claim {question_id}",
        source=f"https://docs.example.test/{question_id}",
        source_date="2026-08-20",
        retrieved_at="2026-08-21T09:00:00+08:00",
        evidence_strength=p4.EvidenceStrength.HIGH,
        contradictions=[],
        confidence=0.9,
        supporting_excerpt=f"Documentation supports capability {question_id}.",
    )


def candidate(candidate_id, lens, mechanism):
    value = p1.Candidate(
        id=candidate_id,
        title=f"Option {candidate_id}",
        one_liner=f"Direction {candidate_id}",
        core_mechanism=mechanism,
        target_user=p0.KnowledgeItem("product team", p0.KnowledgeStatus.KNOWN),
        value_created=f"value {candidate_id}",
        why_distinct=f"distinct {candidate_id}",
        key_assumptions=[
            p0.KnowledgeItem(
                f"assumption {candidate_id}", p0.KnowledgeStatus.ASSUMPTION
            )
        ],
        main_dependency=p0.KnowledgeItem(
            f"dependency {candidate_id}", p0.KnowledgeStatus.UNKNOWN
        ),
        exploration_lens=lens,
        complexity=p1.CandidateComplexity.LOW,
    )
    return p1._json_ready(value)


def worker_tasks(value):
    assignments = [
        p5.ExplorationAssignment("worker-1", p1.ExplorationLens.BASELINE),
        p5.ExplorationAssignment("worker-2", p1.ExplorationLens.ANALOGY),
        p5.ExplorationAssignment("worker-3", p1.ExplorationLens.SUBSTITUTION),
    ]
    return p5.build_exploration_tasks(
        value,
        assignments,
        hard_constraints=["must remain reversible"],
    )


def worker_success(worker_id, lens, candidate_id, mechanism):
    return p5.WorkerExecutionResult(
        worker_id=worker_id,
        kind=p5.WorkerKind.EXPLORATION,
        success=True,
        output=p5.ExplorationWorkerOutput(
            [candidate(candidate_id, lens, mechanism)]
        ),
    )


def signals():
    return p5.ParallelGateSignals(
        independent_dimensions=3,
        outputs_independently_generatable=True,
        synthesis_cost=1.0,
        duplicated_context_cost=3.0,
    )

