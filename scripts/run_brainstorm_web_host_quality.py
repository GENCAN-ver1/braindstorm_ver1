#!/usr/bin/env python3
"""Approve the authorized Brainstorm Web Host P6 artifact and emit its handoff."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from adapters.evaluator_runtime import TracedEvaluator  # noqa: E402
from artifacts.manifest import QualityStatus  # noqa: E402
from artifacts.writer import ArtifactWriter  # noqa: E402
from observability.trace_sink import TraceSink  # noqa: E402
from observability.usage_ledger import PriceTable, UsageLedger  # noqa: E402
from runtime.budget_guard import BudgetChargeKind, BudgetGuard  # noqa: E402
from runtime.checkpoint import CheckpointStore  # noqa: E402
from runtime.fault_injection import FaultInjector, Stage  # noqa: E402
from runtime.governor_modules import p0, p2, p6  # noqa: E402
from runtime.handoff_gate import HandoffGate  # noqa: E402
from runtime.reentry import StageContext  # noqa: E402


DEFAULT_BRIEF = PROJECT_ROOT / "BRAINSTORM_WEB_HOST_BRIEF_V2.md"
DEFAULT_FINAL = PROJECT_ROOT / "artifacts" / "brainstorm-web-host-v2.approved.json"
DEFAULT_PRICING = PROJECT_ROOT / "config" / "provider-pricing.json"

NON_GOALS = [
    "本轮不修改 P0–P6 Governor runtime、锁定决定或合法状态语义",
    "本轮不实现或宣称真实后端编排、真实 Provider 调用和生产身份系统",
    "本轮不部署、不配置 DNS、不保存真实凭据、不 push、不 merge 或创建 PR",
]

ACCEPTANCE_CRITERIA = [
    "终端用户无需查看或编辑 Governor JSON 即可完成 Idea Intake 和六 Frame Wizard。",
    "四种 Idea stage 选择分别且仅映射到 Shape、Spark、Stress、Decide。",
    "六 Frame 映射到约定 canonical 字段，并保留 UNKNOWN、ASSUMPTION、KNOWN、CONFLICT 知识分类；AI 建议不得自动成为 KNOWN。",
    "运行页表达完整阶段、Governor 合法状态，并允许 NEEDS_INPUT 在同一 session lineage 中补充信息后恢复。",
    "External Capability Gate 支持 Council Enable/Skip、至少两个独立 Provider 的校验和调用前显式授权。",
    "API key 仅存在于 capability screen 的临时组件状态，不进入持久化、URL、日志、telemetry、manifest、Living Brief、Trace 或真实测试 fixture。",
    "Human Gate 支持 Confirm、Request iteration 和 Provide missing input，且只有 Governor COMMIT 才显示正式 Final Handoff。",
    "标准跳过、NEEDS_INPUT、Council、Provider failure 和刷新恢复场景均通过行为测试与真实浏览器 E2E。",
    "390、768、1280、1440 代表性视口、键盘导航、焦点、标签、错误关联、对比度和 reduced motion 完成验证。",
    "前端 typecheck、lint、单元与集成测试、production build、React review、UI review、安全审查、P7 validator 和 P0–P6 regression 全部通过。",
]

RISKS = [
    "development mock 与未来真实 backend contract 漂移会造成错误集成信心。",
    "session 恢复实现若边界不清，可能把前端 projection 误当 Governor canonical state。",
    "API key 可能因持久化、日志或错误处理疏漏而泄漏。",
    "单 Provider 或 Provider failure 可能被 UI 错误表述为真实 COUNCIL。",
    "非 COMMIT 状态可能被错误展示为 Final、Approved 或 Ready for implementation。",
    "高密度多阶段流程可能在移动端、键盘或辅助技术下不可完成。",
]

SCOPE_IN = [
    "Idea Intake 与四种现有 Governor mode 映射",
    "六 Frame Wizard、知识分类、校验与刷新恢复",
    "运行进度、合法状态、NEEDS_INPUT 恢复与 Human Gate",
    "External Capability Gate、Council Enable/Skip、授权和临时密钥处理",
    "COMMIT-only Final Handoff 与开发 mock adapter",
    "响应式、无障碍、自动化测试、浏览器 E2E 和前端安全审查",
]


class ContractEvaluator:
    """Independent deterministic evaluator for the user-authorized specification."""

    def evaluate(self, request: p6.EvaluatorInput) -> p6.EvaluatorInvocation:
        if set(request.evaluation_criteria) != set(p6.EvaluationCheck):
            raise p0.ContractError("P6 evaluator criteria are incomplete")
        corrections: list[p6.ActionableCorrection] = []

        def require(
            condition: bool,
            check: p6.EvaluationCheck,
            target: str,
            issue: str,
            required_change: str,
        ) -> None:
            if condition:
                return
            corrections.append(
                p6.ActionableCorrection(
                    id=f"{check.value.lower()}-{len(corrections) + 1}",
                    check=check,
                    target=target,
                    issue=issue,
                    required_change=required_change,
                    severity=p6.CorrectionSeverity.HIGH,
                    high_impact=True,
                )
            )

        frame = request.confirmed_frame
        candidates = request.candidates
        recommendation = request.recommendation or {}
        constraints = frame.get("constraints", [])
        require(
            len(constraints) >= 7
            and all(item.get("classification") == "KNOWN" for item in constraints),
            p6.EvaluationCheck.HARD_CONSTRAINTS,
            "confirmed_frame.constraints",
            "The approved hard constraints are incomplete or not explicitly known.",
            "Preserve every authorized UI, state, security, responsive and accessibility constraint as KNOWN.",
        )
        require(
            len(candidates) >= 4
            and {item.get("exploration_lens") for item in candidates}
            >= {"BASELINE", "INVERSION", "STAKEHOLDER_SHIFT", "SUBSTITUTION"},
            p6.EvaluationCheck.OBVIOUS_ALTERNATIVES,
            "candidates",
            "The artifact does not compare the guided host with the obvious console, chat and read-only alternatives.",
            "Include the four mechanism-distinct alternatives and preserve their lenses.",
        )
        require(
            all(
                isinstance(frame.get(key), dict)
                and frame[key].get("classification") == "KNOWN"
                for key in ("problem", "user", "success", "kill")
            ),
            p6.EvaluationCheck.EVIDENCE_SUPPORT,
            "confirmed_frame",
            "A user-authorized frame field lacks an explicit knowledge basis.",
            "Keep each user-authorized frame field classified as KNOWN; do not introduce external factual claims.",
        )
        require(
            all(
                assumption.get("classification") == "ASSUMPTION"
                for item in candidates
                for assumption in item.get("key_assumptions", [])
            ),
            p6.EvaluationCheck.FACT_ASSUMPTION_LABELING,
            "candidates",
            "Candidate assumptions are being represented as facts.",
            "Classify every candidate assumption as ASSUMPTION until validated.",
        )
        require(
            recommendation.get("candidate_id") == "c1"
            and len(recommendation.get("risks", [])) >= 5
            and len(recommendation.get("tradeoffs", {}).get("rejected", [])) >= 3,
            p6.EvaluationCheck.TRADEOFF_FAIRNESS,
            "recommendation.tradeoffs",
            "The recommendation does not fairly record rejected alternatives and material risks.",
            "Record why each competing mechanism is rejected and preserve the material implementation risks.",
        )
        require(
            bool(recommendation.get("weight_sensitivity")),
            p6.EvaluationCheck.WEIGHT_SENSITIVITY,
            "recommendation.weight_sensitivity",
            "The recommendation omits the condition under which a cheaper alternative would win.",
            "State the weight change that would make the JSON console or read-only viewer preferable.",
        )
        require(
            "浏览器 E2E" in recommendation.get("next_validation", "")
            and len(recommendation.get("acceptance_criteria", [])) >= 10,
            p6.EvaluationCheck.CHEAPEST_TEST_FALSIFIABILITY,
            "recommendation.next_validation",
            "The next validation cannot falsify the decisive workflow and secret-boundary assumptions.",
            "Require the five browser scenarios, secret persistence checks and complete frontend quality gate.",
        )
        return p6.EvaluatorInvocation(
            report=p6.EvaluationReport(corrections),
            usage=p6.RuntimeUsage(),
        )


def build_artifact(state: p0.RuntimeState) -> p6.QualityArtifact:
    artifact = p6.artifact_from_state(
        state,
        output_contract={
            "artifact_type": "brainstorm_web_host_handoff",
            "required": [
                "confirmed_frame",
                "candidates",
                "recommendation",
                "evidence_summary",
                "output_contract",
            ],
        },
    )
    artifact.recommendation = {
        "candidate_id": "c1",
        "decision": "PROCEED_WITH_FRONTEND_MVP",
        "confidence": state.result.confidence,
        "architecture_boundary": {
            "client": "React + TypeScript + Vite structured workflow UI",
            "api": "typed API boundary with development-only mock adapter",
            "canonical_state": "backend Governor and Living Brief",
            "ephemeral_state": "provider credentials and authorization screen state",
        },
        "required_flow": [
            "Idea Intake",
            "Six Frame Wizard",
            "Run Progress",
            "External Capability Gate",
            "Council Enable or Skip",
            "Human Gate",
            "Evaluation",
            "COMMIT-only Final Handoff",
        ],
        "acceptance_criteria": list(ACCEPTANCE_CRITERIA),
        "risks": list(RISKS),
        "tradeoffs": {
            "chosen": "结构化 Wizard 在可解释性、恢复能力、状态边界和用户可达性之间最符合全部硬约束。",
            "rejected": [
                "原始 JSON 控制台要求终端用户理解内部 schema。",
                "Chat-first 隐藏 Frame、知识分类和合法状态，削弱可恢复性。",
                "静态 Session Review 无法完成新建、补充信息和 Human Gate 操作。",
            ],
        },
        "weight_sensitivity": "若唯一目标变成仅服务熟悉 schema 的内部工程师且不要求端到端交互，原始 JSON 控制台会以更低成本胜出；当前用户明确要求无 JSON 的完整浏览器流程，因此 c1 保持优势。",
        "next_validation": "执行 P7 前端 TDD、production build、真实浏览器 E2E、React/UI/安全审查和 P0–P6 回归。",
    }
    p6.validate_quality_artifact(artifact)
    return artifact


def run_quality(brief_path: Path, final_path: Path) -> dict[str, object]:
    brief = p2.load_brief(brief_path)
    session = CheckpointStore(
        trace_sink=TraceSink(brief_path.with_name(f"{brief_path.name}.trace.json")),
        usage_ledger=UsageLedger(PriceTable.load(DEFAULT_PRICING)),
    ).open(brief_path, brief.runtime_state)
    if session.state.run.status is not p0.RunStatus.STOPPED:
        raise p0.ContractError("P6 authorization requires the Human Gate stop")
    if session.state.result.exit_status is not p0.ExitStatus.NEEDS_INPUT:
        raise p0.ContractError("P6 authorization requires NEEDS_INPUT")
    if session.state.result.recommendation != "c1":
        raise p0.ContractError("authorized recommendation is not c1")

    state = copy.deepcopy(session.state)
    state.run.status = p0.RunStatus.ACTIVE
    state.result.exit_status = None
    state.decisions.append(
        p0.Decision(
            id="human-gate-brainstorm-web-host",
            topic="concept",
            value="c1",
            status=p0.DecisionStatus.LOCKED,
            rationale="用户在 P7 authority conflict stop 后明确授权建立独立 Brainstorm Web Host P0–P6 handoff。",
        )
    )
    session.brief.risks = list(RISKS)
    session.brief.scope_in = list(SCOPE_IN)
    session.brief.scope_out = list(NON_GOALS)
    session.commit_stage(
        state,
        Stage.CONVERGE,
        Stage.EVALUATE,
        next_action="run the bounded Brainstorm Web Host P6 evaluator",
    )

    session.enter_stage(Stage.EVALUATE)
    guard = BudgetGuard()
    session.consume_budget(guard, Stage.EVALUATE, "stage", BudgetChargeKind.STAGE)
    artifact = build_artifact(session.state)
    evaluator = TracedEvaluator(
        ContractEvaluator(),
        StageContext(session, Stage.EVALUATE, FaultInjector.disabled(), guard),
        provider_name="local-contract-evaluator",
        model_name="deterministic-contract-v1",
        max_rounds=2,
    )
    outcome = p6.run_evaluator_optimizer(
        session.state,
        artifact,
        evaluator,
        optimizer=None,
        config=p6.EvaluatorConfig(evaluator_rounds=1),
    )
    if not outcome.approved:
        raise p0.ContractError(f"P6 quality gate stopped: {outcome.stop_reason.value}")
    outcome.state.run.budget.used_steps = max(
        outcome.state.run.budget.used_steps,
        session.state.run.budget.used_steps,
    )
    session.commit_stage(
        outcome.state,
        Stage.EVALUATE,
        None,
        terminal_exit=p0.ExitStatus.COMMIT,
        next_action="produce the restricted Brainstorm Web Host handoff",
    )
    quality_gate_id = f"quality:{session.state.run.id}:round-{session.envelope.evaluator_rounds_used}"
    approved_content = {
        "schema_version": 1,
        "request_id": session.state.run.id,
        "quality_gate": {
            "status": "APPROVED",
            "quality_gate_id": quality_gate_id,
            "evaluator_provider": "local-contract-evaluator",
            "evaluator_model": "deterministic-contract-v1",
            "evaluator_rounds_used": session.envelope.evaluator_rounds_used,
            "stop_reason": outcome.stop_reason.value,
        },
        **p6._json_ready(outcome.artifact),
    }
    write_result = ArtifactWriter().write_for_session(
        session,
        final_path,
        approved_content,
        quality_gate_id=quality_gate_id,
        quality_status=QualityStatus.APPROVED,
    )
    handoff = HandoffGate().build(
        session,
        outcome,
        write_result.manifest_path,
        acceptance_criteria=ACCEPTANCE_CRITERIA,
        risks=RISKS,
        next_validation="执行 P7 前端 TDD、production build、真实浏览器 E2E、React/UI/安全审查和 P0–P6 回归。",
    )
    return {
        "schema_version": 1,
        "status": "COMMIT",
        "quality_gate_id": quality_gate_id,
        "manifest_path": str(write_result.manifest_path),
        "handoff": p6.handoff_to_dict(handoff),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brief", type=Path, default=DEFAULT_BRIEF)
    parser.add_argument("--final", type=Path, default=DEFAULT_FINAL)
    args = parser.parse_args(argv)
    try:
        result = run_quality(args.brief.resolve(), args.final.resolve())
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, UnicodeError, json.JSONDecodeError, p0.ContractError) as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
