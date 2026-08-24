#!/usr/bin/env python3
"""Create the P6 authority for the real DeepSeek Web Host vertical slice."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from runtime.config_loader import load_config  # noqa: E402
from runtime.full_cycle import FullCycleRunner  # noqa: E402
from runtime.governor_modules import p6  # noqa: E402
import scripts.run_brainstorm_web_host_quality as quality  # noqa: E402


REQUEST_ID = "brainstorm-web-host-deepseek-v3"
BRIEF_PATH = PROJECT_ROOT / "BRAINSTORM_WEB_HOST_DEEPSEEK_BRIEF.md"
TRACE_PATH = PROJECT_ROOT / "BRAINSTORM_WEB_HOST_DEEPSEEK_BRIEF.md.trace.json"
FINAL_PATH = PROJECT_ROOT / "artifacts" / "brainstorm-web-host-deepseek-v3.approved.json"
HANDOFF_PATH = PROJECT_ROOT / "artifacts" / "brainstorm-web-host-deepseek-v3.p6-handoff.json"
SOURCE_REQUEST = PROJECT_ROOT / "brainstorm-web-host.brainstorm.json"
SOURCE_CONFIG = PROJECT_ROOT / "config" / "brainstorm-web-host.yaml"

NON_GOALS = [
    "本轮不修改 P0–P6 Governor runtime、锁定决定或合法状态语义",
    "本轮只接入固定官方 DeepSeek deepseek-v4-pro；不开放任意 Provider URL、不实现真实 multi-provider Council 或生产身份系统",
    "本轮不部署、不配置 DNS、不把真实凭据写入仓库或浏览器、不 push、不 merge 或创建 PR",
]

ACCEPTANCE_CRITERIA = [
    "终端用户无需查看或编辑 Governor JSON 即可完成 Idea Intake 和六 Frame Wizard。",
    "四种 Idea stage 选择分别且仅映射到 Shape、Spark、Stress、Decide。",
    "六 Frame 映射到约定 canonical 字段，并保留 UNKNOWN、ASSUMPTION、KNOWN、CONFLICT 知识分类；AI 建议不得自动成为 KNOWN。",
    "运行页表达完整阶段、Governor 合法状态，并允许 NEEDS_INPUT 在同一 session lineage 中补充信息后恢复。",
    "生产路径通过同源服务端 typed BrainstormApi 调用固定官方 DeepSeek deepseek-v4-pro；DEEPSEEK_API_KEY 只从服务端环境变量解析。",
    "浏览器 bundle、sessionStorage、localStorage、URL、日志、telemetry、manifest、Living Brief、Trace、git 和测试 fixture 均不得包含真实 DeepSeek 凭据。",
    "真实 start run 必须产生经 schema 验证的候选、挑战、收敛与 Human Gate review；Provider usage 来自真实响应，缺失时不得估算。",
    "Human Gate Confirm 必须经过独立 bounded evaluator；只有 Governor COMMIT 才显示正式 Final Handoff。",
    "DeepSeek 超时、429、5xx、无效 JSON 或 schema failure 必须返回可恢复且脱敏的错误，不得泄漏响应体、密钥、stack 或内部路径。",
    "development mock 仅限 test/development 显式模式，production path 不得回退或伪装成真实 Governor 结果。",
    "标准路径、NEEDS_INPUT、真实 DeepSeek run、Provider failure、Human Gate、COMMIT handoff 和刷新恢复均通过自动化与真实浏览器 E2E。",
    "390、768、1280、1440 代表性视口、键盘导航、焦点、标签、错误关联、对比度和 reduced motion 完成验证。",
    "前后端 typecheck、lint、单元与集成测试、production build、真实 Provider smoke、React/UI/安全审查、P7 validator 和 P0–P6 regression 全部通过。",
]

RISKS = [
    "模型输出可能不满足 Governor schema，必须在 canonical state 之前验证并安全失败。",
    "Provider 延迟、限流或服务失败可能中断 run，必须有超时、有限重试和幂等 revision。",
    "Prompt injection 可能试图把用户内容变成模型指令，所有输入必须按 DATA_ONLY 处理。",
    "服务端密钥可能经日志、错误或浏览器 payload 泄漏。",
    "任意 Provider URL 会形成 SSRF，因此 endpoint 与 model 必须固定并在服务端配置。",
    "单一 DeepSeek Provider 不能被表述为 multi-provider Council。",
]

SCOPE_IN = [
    "保留已验收 React Web Host、六 Frame、合法状态、NEEDS_INPUT、Human Gate 与 COMMIT-only handoff",
    "新增同源本地 HTTP backend，backend 成为 session 与 Governor workflow truth",
    "固定官方 DeepSeek endpoint、deepseek-v4-pro 和 DEEPSEEK_API_KEY 服务端 secret source",
    "真实模型生成、bounded evaluator、usage receipt、脱敏错误与服务器端非 secret session persistence",
    "真实 Provider smoke、浏览器 E2E、安全审查和 P0–P7 regression",
]


def _request() -> dict[str, object]:
    request = json.loads(SOURCE_REQUEST.read_text(encoding="utf-8"))
    request["request_id"] = REQUEST_ID
    request["text"] = (
        "Replace the approved development simulation with a local, server-side "
        "DeepSeek-backed Brainstorm vertical slice while preserving Governor semantics."
    )
    core = request["core"]
    context = core["context"]
    context["requested_outcome"] = {
        "statement": "交付本地可运行、服务端调用 DeepSeek v4 Pro 并完成 Governor 到 Final Handoff 的真实 Web vertical slice",
        "classification": "KNOWN",
    }
    context["current_idea"] = {
        "statement": "保留 React typed BrainstormApi，新增同源本地 backend，通过固定 DeepSeek endpoint 生成并评估受 Governor schema 约束的内容",
        "classification": "KNOWN",
    }
    context["constraints"] = [
        {"statement": item, "classification": "KNOWN"}
        for item in NON_GOALS + [
            "DEEPSEEK_API_KEY 只在服务端 call-time 解析且不得进入浏览器或 durable artifact",
            "DeepSeek endpoint 与 deepseek-v4-pro model 固定，用户输入不能控制 outbound URL",
        ]
    ]
    context["assets"].append(
        {
            "statement": "仓库已有 OpenAI-compatible evaluator、Provider usage、Trace、ArtifactWriter 与 HandoffGate",
            "classification": "KNOWN",
        }
    )

    frame = core["problem_frame"]
    frame["problem_statement"] = {
        "statement": "已验收 Web Host 仍由 development mock 生成结果，尚不能证明真实模型、服务端 canonical state 与 Governor handoff 能端到端运作",
        "classification": "KNOWN",
    }
    frame["desired_change"] = {
        "statement": "从显式模拟切换为服务端 DeepSeek v4 Pro 生成和 bounded evaluator，同时保持现有用户流程、合法状态与安全边界",
        "classification": "KNOWN",
    }
    frame["hard_constraints"].extend(
        [
            {"statement": ACCEPTANCE_CRITERIA[4], "classification": "KNOWN"},
            {"statement": ACCEPTANCE_CRITERIA[5], "classification": "KNOWN"},
            {"statement": ACCEPTANCE_CRITERIA[8], "classification": "KNOWN"},
            {"statement": ACCEPTANCE_CRITERIA[9], "classification": "KNOWN"},
        ]
    )
    frame["success_metric"] = {
        "statement": ACCEPTANCE_CRITERIA[-1],
        "classification": "KNOWN",
    }
    frame["kill_criterion"] = {
        "statement": "任一真实调用未经过服务端、密钥或响应体泄漏、任意 URL 可被请求、模型输出未经 schema 验证、非 COMMIT 显示 Final Handoff，或真实 smoke/E2E 未通过",
        "classification": "KNOWN",
    }
    frame["non_goals"] = [
        {"statement": item, "classification": "KNOWN"} for item in NON_GOALS
    ]
    frame["time_horizon"] = {
        "statement": "本次 P7 连续执行周期内完成本地真实 DeepSeek vertical slice 与验收",
        "classification": "KNOWN",
    }

    c1 = next(item for item in core["candidates"] if item["id"] == "c1")
    c1.update(
        {
            "title": "服务端 DeepSeek Governor Bridge",
            "one_liner": "以固定 DeepSeek v4 Pro 服务端调用生成结构化内容，并复用 Governor、Evaluator 与 Handoff gate。",
            "core_mechanism": "same-origin server bridge with fixed DeepSeek model, validated structured generation, durable Governor state and bounded evaluation",
            "value_created": "把已验收 UI 从模拟升级为真实模型 vertical slice，同时保持 Governor 为唯一 workflow truth。",
            "why_distinct": "模型与 secret 只在服务端，输出在进入 canonical state 前通过既有 schema，最终 handoff 仍由 Governor gate 产生。",
            "key_assumptions": [
                {
                    "statement": "DeepSeek v4 Pro 可稳定返回满足受限 JSON contract 的候选与评估结果",
                    "classification": "ASSUMPTION",
                }
            ],
            "main_dependency": {
                "statement": "仓库现有 OpenAI-compatible adapter、P1 schema、P6 evaluator、ArtifactWriter 与 HandoffGate 可被本地 backend 复用",
                "classification": "KNOWN",
            },
            "complexity": "HIGH",
        }
    )
    c1_challenge = next(item for item in core["challenges"] if item["candidate_id"] == "c1")
    c1_challenge["blindspots"] = [
        "模型输出可能通过 JSON 语法但不满足 Governor 语义 schema",
        "服务端持久化、错误与日志可能意外泄漏 Provider 数据",
        "重复 start 或 Human Gate 提交可能产生重复计费",
    ]
    c1_challenge["assumption_audit"] = copy.deepcopy(c1["key_assumptions"])
    c1_challenge["pressure_test"] = [
        "Steelman：同源服务端 bridge 是最小可验证路径，可复用现有 Governor 与前端合同。",
        "依赖失败：DeepSeek 不可用时必须保持 session 可恢复且不得生成伪造结果。",
        "边界测试：恶意 idea/Frame 内容必须始终作为 DATA_ONLY，不能改变 system contract。",
    ]
    c1_assessment = next(item for item in core["assessments"] if item["candidate_id"] == "c1")
    c1_assessment.update({"feasibility": 0.8, "evidence_confidence": 0.75, "risk": 0.35})
    core["cheapest_test"] = (
        "用已配置 DEEPSEEK_API_KEY 发起一个受限真实 run，验证响应 model/usage、schema、Human Gate evaluator、COMMIT handoff、重启恢复和 secret scan。"
    )
    return request


def _build_artifact(state):
    artifact = p6.artifact_from_state(
        state,
        output_contract={
            "artifact_type": "brainstorm_web_host_deepseek_handoff",
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
        "decision": "PROCEED_WITH_REAL_DEEPSEEK_VERTICAL_SLICE",
        "confidence": state.result.confidence,
        "architecture_boundary": {
            "client": "React + TypeScript browser projection using typed HTTP BrainstormApi",
            "server": "same-origin local host with durable non-secret session state",
            "provider": "fixed https://api.deepseek.com / deepseek-v4-pro",
            "secret_source": "DEEPSEEK_API_KEY resolved server-side only",
            "canonical_state": "P0-P6 Living Brief, Trace, artifact and handoff gates",
        },
        "required_flow": [
            "Idea Intake",
            "Six Frame Wizard",
            "Real DeepSeek Run",
            "External Capability Gate",
            "Human Gate",
            "Bounded Evaluator",
            "COMMIT-only Final Handoff",
        ],
        "acceptance_criteria": list(ACCEPTANCE_CRITERIA),
        "risks": list(RISKS),
        "tradeoffs": {
            "chosen": "固定同源服务端 DeepSeek bridge 最小化 secret、SSRF 与 contract drift，同时提供真实模型证据。",
            "rejected": [
                "浏览器直连会暴露 DEEPSEEK_API_KEY。",
                "任意 OpenAI-compatible base URL 会扩大 SSRF 与 secret transmission boundary。",
                "继续 development mock 无法满足真实模型运作要求。",
            ],
        },
        "weight_sensitivity": "若不再要求真实 Provider 与 server canonical state，development mock 成本更低；当前用户已明确选择 DeepSeek，因此真实 bridge 必须胜出。",
        "next_validation": "执行真实 DeepSeek smoke、服务端/前端自动化、浏览器 E2E、secret/security review、production build 和 P0–P7 regression。",
    }
    p6.validate_quality_artifact(artifact)
    return artifact


def main() -> int:
    for path in (BRIEF_PATH, TRACE_PATH, FINAL_PATH, FINAL_PATH.with_name(FINAL_PATH.name + ".manifest.json"), HANDOFF_PATH):
        if path.exists():
            raise RuntimeError(f"refusing to overwrite existing authority artifact: {path}")

    config = load_config(SOURCE_CONFIG)
    summary = FullCycleRunner(config, config_base_dir=SOURCE_CONFIG.parent).run(
        _request(), brief_path=BRIEF_PATH
    )
    if summary.exit_status != "NEEDS_INPUT":
        raise RuntimeError(f"authority run stopped at {summary.exit_status}, expected NEEDS_INPUT")

    quality.NON_GOALS = NON_GOALS
    quality.ACCEPTANCE_CRITERIA = ACCEPTANCE_CRITERIA
    quality.RISKS = RISKS
    quality.SCOPE_IN = SCOPE_IN
    quality.build_artifact = _build_artifact
    result = quality.run_quality(BRIEF_PATH, FINAL_PATH)
    HANDOFF_PATH.write_text(
        json.dumps(result["handoff"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "brief_path": str(BRIEF_PATH),
                "approved_artifact_path": str(FINAL_PATH),
                "handoff_path": str(HANDOFF_PATH),
                "quality_gate_id": result["quality_gate_id"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
