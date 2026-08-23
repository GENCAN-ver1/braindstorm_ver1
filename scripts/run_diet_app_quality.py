#!/usr/bin/env python3
"""Run the bounded real-provider P6 gate for the diet-app concept artifact."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


PROJECT_ROOT = Path(__file__).parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from adapters.evaluator_runtime import TracedEvaluator  # noqa: E402
from adapters.openai_evaluator import (  # noqa: E402
    OpenAICompatibleEvaluatorConfig,
    OpenAICompatibleObservedEvaluatorAdapter,
)
from artifacts.manifest import QualityStatus  # noqa: E402
from artifacts.writer import ArtifactWriter  # noqa: E402
from observability.events import ActivationKind  # noqa: E402
from observability.trace_sink import TraceSink  # noqa: E402
from observability.usage_ledger import PriceTable, UsageLedger  # noqa: E402
from runtime.budget_guard import BudgetChargeKind, BudgetGuard  # noqa: E402
from runtime.checkpoint import CheckpointStore  # noqa: E402
from runtime.fault_injection import FaultInjector, Stage  # noqa: E402
from runtime.governor_modules import p0, p2, p6  # noqa: E402
from runtime.handoff_gate import HandoffGate  # noqa: E402
from runtime.reentry import StageContext  # noqa: E402


DEFAULT_BRIEF = PROJECT_ROOT / "DIET_APP_CONCEPT_BRIEF_V3.md"
DEFAULT_DRAFT = PROJECT_ROOT / "staging" / "diet-app-quality-artifact.json"
DEFAULT_FINAL = PROJECT_ROOT / "artifacts" / "diet-app-concept-v3.approved.json"
DEFAULT_PRICING = PROJECT_ROOT / "config" / "provider-pricing.json"

RISKS = [
    "食物或分量输入错误可能在闭环中放大并破坏信任。",
    "高频纠偏可能带来被控制感、饮食焦虑或通知疲劳。",
    "首周人工响应延迟可能使下一餐建议失去时效性。",
    "功能与现有照片记录、计划和目标更新产品重叠，差异化仍需用户验证。",
    "方向性建议仍可能被用户误解为医疗或健康效果承诺。",
]

SCOPE_IN = [
    "初始化目标、主观基线、作息、外食频率、偏好、过敏或禁忌",
    "拍照或食物列表记录与用户分量确认",
    "人工后台生成方向性下一餐建议",
    "用户可控通知、异常场景降级和日历行为复盘",
    "七天 Wizard-of-Oz 行为与决策成本验证",
]

SCOPE_OUT = [
    "全自动食物识别与精确营养计算",
    "医疗诊断、疾病管理或治疗建议",
    "用七天结果宣称稳定身体或精神健康改善",
    "商业模式、社交功能、运动管理和完整工程架构",
]

CHEAPEST_TEST = (
    "招募目标 8-12 名、最低 8 名目标用户，连续七天使用可点击原型与透明标注的"
    "人工后台；用户记录后确认食物和标准份量，后台 10 分钟内返回方向性下一餐建议。"
    "主要检验决策成本、继续使用意愿、建议跟随率和确认完成率，并以焦虑/被控制感、"
    "响应延迟和医疗越界作为安全失败信号；身体与精神状态变化仅作探索性自报记录。"
)


def load_artifact(path: Path) -> tuple[dict[str, Any], p6.QualityArtifact]:
    value = _mapping(json.loads(path.read_text(encoding="utf-8")), str(path))
    evidence = []
    for index, item_value in enumerate(_list(value.get("evidence_summary"), "evidence_summary")):
        item = _mapping(item_value, f"evidence_summary[{index}]")
        evidence.append(
            p6.EvidenceSummaryItem(
                id=_string(item.get("id"), f"evidence_summary[{index}].id"),
                claim=_string(item.get("claim"), f"evidence_summary[{index}].claim"),
                source=_optional_string(item.get("source"), f"evidence_summary[{index}].source"),
                evidence_strength=_optional_string(
                    item.get("evidence_strength"),
                    f"evidence_summary[{index}].evidence_strength",
                ),
                contradictions=[
                    _string(value, f"evidence_summary[{index}].contradictions")
                    for value in _list(
                        item.get("contradictions", []),
                        f"evidence_summary[{index}].contradictions",
                    )
                ],
                treatment=p6.ExternalContentTreatment(
                    item.get("treatment", "DATA_ONLY")
                ),
            )
        )
    artifact = p6.QualityArtifact(
        confirmed_frame=copy.deepcopy(
            dict(_mapping(value.get("confirmed_frame"), "confirmed_frame"))
        ),
        candidates=copy.deepcopy(_list(value.get("candidates"), "candidates")),
        recommendation=copy.deepcopy(
            dict(_mapping(value.get("recommendation"), "recommendation"))
        ),
        evidence_summary=evidence,
        output_contract=copy.deepcopy(
            dict(_mapping(value.get("output_contract"), "output_contract"))
        ),
    )
    p6.validate_quality_artifact(artifact)
    return dict(value), artifact


def prepare_session(brief_path: Path, artifact: p6.QualityArtifact):
    brief = p2.load_brief(brief_path)
    trace_sink = TraceSink(brief_path.with_name(f"{brief_path.name}.trace.json"))
    usage_ledger = UsageLedger(PriceTable.load(DEFAULT_PRICING))
    session = CheckpointStore(
        trace_sink=trace_sink, usage_ledger=usage_ledger
    ).open(brief_path, brief.runtime_state)

    if session.state.run.status is p0.RunStatus.COMPLETED:
        raise p0.ContractError("quality workflow is already committed")
    if session.state.run.status is p0.RunStatus.STOPPED:
        allowed = {p0.ExitStatus.NEEDS_INPUT, p0.ExitStatus.ITERATE}
        if session.state.result.exit_status not in allowed:
            raise p0.ContractError("stopped quality workflow cannot be resumed")
        if session.envelope.evaluator_rounds_used >= 2:
            raise p0.ContractError("quality workflow exhausted the evaluator cap")
        state = copy.deepcopy(session.state)
        state.run.status = p0.RunStatus.ACTIVE
        state.result.exit_status = None
        state.result.cheapest_test = CHEAPEST_TEST
        _merge_evidence(state, artifact)
        _lock_confirmed_concept(state)
        session.brief.risks = list(RISKS)
        session.brief.scope_in = list(SCOPE_IN)
        session.brief.scope_out = list(SCOPE_OUT)
        completed_stage = (
            Stage.CONVERGE
            if session.state.result.exit_status is p0.ExitStatus.NEEDS_INPUT
            else Stage.EVALUATE
        )
        session.commit_stage(
            state,
            completed_stage,
            Stage.EVALUATE,
            next_action="run the bounded P6 evaluator on the refined c2 artifact",
        )
        if session.envelope.evaluator_rounds_used == 0:
            session.record_gate_decision(
                Stage.CHALLENGE,
                "research",
                True,
                "five citation-checked DATA_ONLY records informed convergence",
            )
            session.record_activation(Stage.CHALLENGE, ActivationKind.P4_RESEARCH)
            session.record_gate_decision(
                Stage.CHALLENGE,
                "council",
                True,
                "DeepSeek and Kimi independently succeeded and returned REFINE",
            )
            session.record_activation(Stage.CHALLENGE, ActivationKind.COUNCIL)

    if session.envelope.next_stage != Stage.EVALUATE.value:
        raise p0.ContractError("checkpoint is not ready for EVALUATE")
    session.enter_stage(Stage.EVALUATE)
    guard = BudgetGuard()
    session.consume_budget(guard, Stage.EVALUATE, "stage", BudgetChargeKind.STAGE)
    return session, guard


def run_quality(
    brief_path: Path,
    draft_path: Path,
    final_path: Path,
) -> dict[str, Any]:
    draft, artifact = load_artifact(draft_path)
    session, guard = prepare_session(brief_path, artifact)
    config = OpenAICompatibleEvaluatorConfig(
        base_url="https://api.deepseek.com",
        model="deepseek-v4-pro",
        credential_env="DEEPSEEK_API_KEY",
        timeout_seconds=180,
        max_output_tokens=4096,
        provider_options={"thinking": {"type": "disabled"}},
    )
    evaluator = TracedEvaluator(
        OpenAICompatibleObservedEvaluatorAdapter(config),
        StageContext(session, Stage.EVALUATE, FaultInjector.disabled(), guard),
        provider_name="deepseek",
        model_name="deepseek-v4-pro",
        max_rounds=2,
    )
    outcome = p6.run_evaluator_optimizer(
        session.state,
        artifact,
        evaluator,
        optimizer=None,
        config=p6.EvaluatorConfig(evaluator_rounds=1),
    )
    outcome.state.run.budget.used_steps = max(
        outcome.state.run.budget.used_steps,
        session.state.run.budget.used_steps,
    )
    if not outcome.approved:
        session.commit_stage(
            outcome.state,
            Stage.EVALUATE,
            None,
            terminal_exit=outcome.state.result.exit_status,
            next_action="apply the field-targeted evaluator corrections and rerun once",
        )
        return {
            "schema_version": 1,
            "status": outcome.state.result.exit_status.value,
            "stop_reason": outcome.stop_reason.value,
            "evaluator_rounds_used": session.envelope.evaluator_rounds_used,
            "corrections": [p6._json_ready(item) for item in outcome.remaining_corrections],
        }

    session.commit_stage(
        outcome.state,
        Stage.EVALUATE,
        None,
        terminal_exit=p0.ExitStatus.COMMIT,
        next_action="produce the restricted approved handoff",
    )
    quality_gate_id = (
        f"quality:{session.state.run.id}:round-{session.envelope.evaluator_rounds_used}"
    )
    approved_content = {
        "schema_version": draft.get("schema_version", 1),
        "request_id": draft.get("request_id"),
        "quality_gate": {
            "status": "APPROVED",
            "quality_gate_id": quality_gate_id,
            "evaluator_provider": "deepseek",
            "evaluator_model": "deepseek-v4-pro",
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
        acceptance_criteria=[
            "至少 60% 用户报告饮食决策成本下降。",
            "至少 50% 用户表达继续使用意愿。",
            "至少 60% 已确认建议被执行或部分执行。",
            "食物与分量确认完成率至少 80%。",
            "所有建议通过非医疗边界检查，且没有严重焦虑或被控制感报告。",
        ],
        risks=RISKS,
        next_validation=artifact.recommendation["next_validation"],
    )
    return {
        "schema_version": 1,
        "status": "COMMIT",
        "quality_gate_id": quality_gate_id,
        "manifest_path": str(write_result.manifest_path),
        "handoff": p6.handoff_to_dict(handoff),
    }


def _merge_evidence(state: p0.RuntimeState, artifact: p6.QualityArtifact) -> None:
    existing = {item.id for item in state.evidence}
    for item in artifact.evidence_summary:
        if item.id in existing:
            continue
        classification = (
            p0.KnowledgeStatus.KNOWN
            if item.id == "e1-personalization-can-change-diet"
            else p0.KnowledgeStatus.ASSUMPTION
        )
        state.evidence.append(
            p0.EvidenceRecord(
                id=item.id,
                claim=item.claim,
                classification=classification,
                source=item.source,
                metadata={
                    "evidence_strength": item.evidence_strength,
                    "contradictions": list(item.contradictions),
                    "treatment": "DATA_ONLY",
                },
            )
        )
        existing.add(item.id)
    council_id = "council-c2-refine-consensus"
    if council_id not in existing:
        state.evidence.append(
            p0.EvidenceRecord(
                id=council_id,
                claim=(
                    "DeepSeek 与 Kimi 独立评审均建议保留 c2 但收缩首周范围，"
                    "加入人工复核、用户确认、非医疗边界和行为验证护栏。"
                ),
                classification=p0.KnowledgeStatus.ASSUMPTION,
                source="evidence/diet-app-council-synthesis.json",
                metadata={"treatment": "DATA_ONLY", "council_label": "COUNCIL"},
            )
        )


def _lock_confirmed_concept(state: p0.RuntimeState) -> None:
    if any(
        item.status is p0.DecisionStatus.LOCKED
        and item.topic.casefold() in {"concept", "locked concept", "locked_concept"}
        for item in state.decisions
    ):
        return
    state.decisions.append(
        p0.Decision(
            id="human-gate-c2",
            topic="concept",
            value="c2",
            status=p0.DecisionStatus.LOCKED,
            rationale=(
                "用户明确确认 c2；Council 只收缩原型边界和验证方式，不改变方向。"
            ),
        )
    )


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise p0.ContractError(f"{path} must be an object")
    return value


def _list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise p0.ContractError(f"{path} must be an array")
    return value


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise p0.ContractError(f"{path} must be a non-empty string")
    return value.strip()


def _optional_string(value: Any, path: str) -> str | None:
    if value is None:
        return None
    return _string(value, path)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brief", type=Path, default=DEFAULT_BRIEF)
    parser.add_argument("--draft", type=Path, default=DEFAULT_DRAFT)
    parser.add_argument("--final", type=Path, default=DEFAULT_FINAL)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        result = run_quality(
            args.brief.resolve(), args.draft.resolve(), args.final.resolve()
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "COMMIT" else 2
    except (OSError, UnicodeError, json.JSONDecodeError, p0.ContractError) as exc:
        print(
            json.dumps(
                {"schema_version": 1, "status": "ERROR", "error": str(exc)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
