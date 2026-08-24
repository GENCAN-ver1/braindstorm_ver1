# CONCEPT_BRIEF

<!-- BRAINSTORM_GOVERNOR_STATE_V1_START -->
```json
{
  "assumptions": [
    "DeepSeek v4 Pro 可稳定返回满足受限 JSON contract 的候选与评估结果",
    "熟悉 Governor schema 的内部工程用户",
    "用户具备内部 schema 知识",
    "目标用户能够安全理解并编辑 Governor JSON",
    "偏好自由对话而非显式结构的用户",
    "可靠地从自由文本提取全部必填 Frame",
    "隐式 Frame 不会降低可解释性、恢复能力和知识分类准确性",
    "只需要审计既有 run 的 reviewer",
    "所有用户已有由其他入口创建的合法 session",
    "只读审阅足以替代新建和恢复 brainstorm session"
  ],
  "cheapest_test": "用已配置 DEEPSEEK_API_KEY 发起一个受限真实 run，验证响应 model/usage、schema、Human Gate evaluator、COMMIT handoff、重启恢复和 secret scan。",
  "constraints": [
    "Idea stage 只能映射到 Shape、Spark、Stress、Decide 四种现有模式",
    "六 Frame 必须映射 target_user、core_task、desired_change、hard_constraints、success_metrics、abandonment_criteria、non_goals 和 validation_horizon，并保留知识分类",
    "运行页必须表达 Governor 阶段、NEEDS_INPUT 恢复、External Capability Gate、Council Enable/Skip、Human Gate 和合法状态",
    "只有 Governor 返回 COMMIT 时才能展示正式 Final Handoff",
    "API key 不得进入浏览器持久化、URL、日志、analytics、Living Brief、Trace、manifest、git 或真实测试 fixture",
    "用户授权必须独立于凭据存在，并在外部 Provider 调用前说明共享内容、接收方和用途",
    "MVP 必须支持 390、768、1280 和 1440 代表性视口，键盘操作、清晰标签、焦点、错误关联和 reduced motion",
    "生产路径通过同源服务端 typed BrainstormApi 调用固定官方 DeepSeek deepseek-v4-pro；DEEPSEEK_API_KEY 只从服务端环境变量解析。",
    "浏览器 bundle、sessionStorage、localStorage、URL、日志、telemetry、manifest、Living Brief、Trace、git 和测试 fixture 均不得包含真实 DeepSeek 凭据。",
    "DeepSeek 超时、429、5xx、无效 JSON 或 schema failure 必须返回可恢复且脱敏的错误，不得泄漏响应体、密钥、stack 或内部路径。",
    "development mock 仅限 test/development 显式模式，production path 不得回退或伪装成真实 Governor 结果。",
    "界面应平静、专业、高信息密度并避免通用 dashboard 和 AI 紫色发光风格",
    "不引入超出 MVP 所需的大型状态管理或组件框架"
  ],
  "current_stage": "EVALUATE",
  "decision_log": [],
  "eliminated_candidates": [],
  "evidence": [],
  "exit_status": "COMMIT",
  "kill_criterion": "任一真实调用未经过服务端、密钥或响应体泄漏、任意 URL 可被请求、模型输出未经 schema 验证、非 COMMIT 显示 Final Handoff，或真实 smoke/E2E 未通过",
  "locked_concept": "c1",
  "next_action": "produce the restricted Brainstorm Web Host handoff",
  "open_questions": [],
  "previous_stop_reason": "COMMIT",
  "problem": "已验收 Web Host 仍由 development mock 生成结果，尚不能证明真实模型、服务端 canonical state 与 Governor handoff 能端到端运作",
  "risks": [
    "模型输出可能不满足 Governor schema，必须在 canonical state 之前验证并安全失败。",
    "Provider 延迟、限流或服务失败可能中断 run，必须有超时、有限重试和幂等 revision。",
    "Prompt injection 可能试图把用户内容变成模型指令，所有输入必须按 DATA_ONLY 处理。",
    "服务端密钥可能经日志、错误或浏览器 payload 泄漏。",
    "任意 Provider URL 会形成 SSRF，因此 endpoint 与 model 必须固定并在服务端配置。",
    "单一 DeepSeek Provider 不能被表述为 multi-provider Council。"
  ],
  "runtime_state": {
    "assumptions": [
      {
        "classification": "ASSUMPTION",
        "statement": "DeepSeek v4 Pro 可稳定返回满足受限 JSON contract 的候选与评估结果"
      },
      {
        "classification": "ASSUMPTION",
        "statement": "熟悉 Governor schema 的内部工程用户"
      },
      {
        "classification": "ASSUMPTION",
        "statement": "用户具备内部 schema 知识"
      },
      {
        "classification": "ASSUMPTION",
        "statement": "目标用户能够安全理解并编辑 Governor JSON"
      },
      {
        "classification": "ASSUMPTION",
        "statement": "偏好自由对话而非显式结构的用户"
      },
      {
        "classification": "ASSUMPTION",
        "statement": "可靠地从自由文本提取全部必填 Frame"
      },
      {
        "classification": "ASSUMPTION",
        "statement": "隐式 Frame 不会降低可解释性、恢复能力和知识分类准确性"
      },
      {
        "classification": "ASSUMPTION",
        "statement": "只需要审计既有 run 的 reviewer"
      },
      {
        "classification": "ASSUMPTION",
        "statement": "所有用户已有由其他入口创建的合法 session"
      },
      {
        "classification": "ASSUMPTION",
        "statement": "只读审阅足以替代新建和恢复 brainstorm session"
      }
    ],
    "candidates": [
      {
        "complexity": "HIGH",
        "core_mechanism": "same-origin server bridge with fixed DeepSeek model, validated structured generation, durable Governor state and bounded evaluation",
        "exploration_lens": "BASELINE",
        "id": "c1",
        "key_assumptions": [
          {
            "classification": "ASSUMPTION",
            "statement": "DeepSeek v4 Pro 可稳定返回满足受限 JSON contract 的候选与评估结果"
          }
        ],
        "main_dependency": {
          "classification": "KNOWN",
          "statement": "仓库现有 OpenAI-compatible adapter、P1 schema、P6 evaluator、ArtifactWriter 与 HandoffGate 可被本地 backend 复用"
        },
        "one_liner": "以固定 DeepSeek v4 Pro 服务端调用生成结构化内容，并复用 Governor、Evaluator 与 Handoff gate。",
        "target_user": {
          "classification": "KNOWN",
          "statement": "不应接触 Governor JSON 的产品构建者与小型团队"
        },
        "title": "服务端 DeepSeek Governor Bridge",
        "value_created": "把已验收 UI 从模拟升级为真实模型 vertical slice，同时保持 Governor 为唯一 workflow truth。",
        "why_distinct": "模型与 secret 只在服务端，输出在进入 canonical state 前通过既有 schema，最终 handoff 仍由 Governor gate 产生。"
      },
      {
        "complexity": "LOW",
        "core_mechanism": "browser JSON console directly exposing governor request and state documents",
        "exploration_lens": "INVERSION",
        "id": "c2",
        "key_assumptions": [
          {
            "classification": "ASSUMPTION",
            "statement": "目标用户能够安全理解并编辑 Governor JSON"
          }
        ],
        "main_dependency": {
          "classification": "ASSUMPTION",
          "statement": "用户具备内部 schema 知识"
        },
        "one_liner": "在浏览器中直接编辑请求 JSON 并展示 runtime JSON。",
        "target_user": {
          "classification": "ASSUMPTION",
          "statement": "熟悉 Governor schema 的内部工程用户"
        },
        "title": "原始 Governor 控制台",
        "value_created": "实现成本最低并最大程度贴近当前 CLI。",
        "why_distinct": "不提供用户友好映射，直接暴露底层合同。"
      },
      {
        "complexity": "HIGH",
        "core_mechanism": "chat-first implicit frame collection with hidden governor progression",
        "exploration_lens": "STAKEHOLDER_SHIFT",
        "id": "c3",
        "key_assumptions": [
          {
            "classification": "ASSUMPTION",
            "statement": "隐式 Frame 不会降低可解释性、恢复能力和知识分类准确性"
          }
        ],
        "main_dependency": {
          "classification": "ASSUMPTION",
          "statement": "可靠地从自由文本提取全部必填 Frame"
        },
        "one_liner": "以单一聊天线程隐式收集 Frame 并在后台驱动 Governor。",
        "target_user": {
          "classification": "ASSUMPTION",
          "statement": "偏好自由对话而非显式结构的用户"
        },
        "title": "Chat-first Brainstorm",
        "value_created": "减少表单感并保持连续对话体验。",
        "why_distinct": "弱化显式 Frame、状态和 gate，可用自然语言补充信息。"
      },
      {
        "complexity": "LOW",
        "core_mechanism": "read-only session viewer replacing interactive workflow with checkpoint inspection",
        "exploration_lens": "SUBSTITUTION",
        "id": "c4",
        "key_assumptions": [
          {
            "classification": "ASSUMPTION",
            "statement": "只读审阅足以替代新建和恢复 brainstorm session"
          }
        ],
        "main_dependency": {
          "classification": "ASSUMPTION",
          "statement": "所有用户已有由其他入口创建的合法 session"
        },
        "one_liner": "只读取现有 Living Brief 并生成阶段与 handoff 报告，不提供运行输入。",
        "target_user": {
          "classification": "ASSUMPTION",
          "statement": "只需要审计既有 run 的 reviewer"
        },
        "title": "静态 Session Review",
        "value_created": "提供最安全的只读状态审查界面。",
        "why_distinct": "用审阅器替代端到端交互产品。"
      }
    ],
    "decisions": [
      {
        "id": "human-gate-brainstorm-web-host",
        "rationale": "用户在 P7 authority conflict stop 后明确授权建立独立 Brainstorm Web Host P0–P6 handoff。",
        "status": "LOCKED",
        "topic": "concept",
        "value": "c1"
      }
    ],
    "deferred": [
      {
        "envelope": {
          "artifact_status": "APPROVED",
          "budget_charges": {
            "idem:v1:15b451af50c9dc42ad37ed2ceb13c5ac02b768ca99a6f2f23f2ccc540fca6f83": 1,
            "idem:v1:20e318f6807c85d68b33de50156700465b608521dc88fbda19ee87c8d6118877": 1,
            "idem:v1:2f0379d7825f5a07bbce6d0eb561416d882e908861f44a2d0ded57e31cb457bf": 1,
            "idem:v1:404a3399db2c1836a7f761d22e68ae66404207cd4be685d04f11aafcfc4c0d9b": 1,
            "idem:v1:5142476935194709f1060e142ce6d270b97251a945b5c22b25fbd27f2a6b1314": 1,
            "idem:v1:64921cc54f9cb8de0533ac076263d2d8279946efc4aeddf2d79f6bffd851bf5f": 1,
            "idem:v1:b0d699b92c6ff71a23b76804b4b54a6f60942b467260c68703c5021a03926bfd": 1,
            "idem:v1:b3b3175a4d879ab2505d66213328fa6359382383b895a1a19746b183fd814ddb": 1,
            "idem:v1:bb981b7a1613b0f1d8df85928db013ab29a0b0657b7b5dad44857f5814bc03d1": 1,
            "idem:v1:f58960676f236bc702405c90dd0d15d3ed0dea1d1575d39441edc3e97f942332": 1
          },
          "evaluator_consumed_keys": [
            "idem:v1:b35e41261957fb5ea96f3dac167f81477ddc38bc3180e7c4cd20bfa42a26418d"
          ],
          "evaluator_request_keys": [
            "idem:v1:b35e41261957fb5ea96f3dac167f81477ddc38bc3180e7c4cd20bfa42a26418d"
          ],
          "evaluator_rounds_used": 1,
          "failure_ledger": [],
          "idempotency_key": "idem:v1:6fc305f983814b79409d2823bbe5f85443bef25d7160701e4e489147462a5ced",
          "in_flight_operation": null,
          "last_completed_stage": "EVALUATE",
          "next_stage": null,
          "operation_receipts": {
            "idem:v1:b35e41261957fb5ea96f3dac167f81477ddc38bc3180e7c4cd20bfa42a26418d": {
              "report": {
                "corrections": []
              },
              "runtime_usage": {
                "token_usage": null,
                "tool_usage": null
              }
            }
          },
          "quality_gate_id": "quality:brainstorm-web-host-deepseek-v3:round-1",
          "recovery_count": 0,
          "revision": 37,
          "run_id": "brainstorm-web-host-deepseek-v3",
          "schema_version": 1,
          "state_hash": "v1:sha256:7218fe53eea4e12f4f0ca2f9c285d33e2529764cbfe528039799499bb5fdb482",
          "trace_cursor": 63,
          "usage_receipt_ids": [
            "usage:v1:sha256:420024c92ce576952e612758dc20e951c53369fdf53d87b461b294a789596f29"
          ],
          "usage_totals": {
            "unavailable_calls": 1
          }
        },
        "type": "brainstorm-governor-checkpoint-v1"
      }
    ],
    "evidence": [],
    "frame": {
      "constraints": [
        {
          "classification": "KNOWN",
          "statement": "Idea stage 只能映射到 Shape、Spark、Stress、Decide 四种现有模式"
        },
        {
          "classification": "KNOWN",
          "statement": "六 Frame 必须映射 target_user、core_task、desired_change、hard_constraints、success_metrics、abandonment_criteria、non_goals 和 validation_horizon，并保留知识分类"
        },
        {
          "classification": "KNOWN",
          "statement": "运行页必须表达 Governor 阶段、NEEDS_INPUT 恢复、External Capability Gate、Council Enable/Skip、Human Gate 和合法状态"
        },
        {
          "classification": "KNOWN",
          "statement": "只有 Governor 返回 COMMIT 时才能展示正式 Final Handoff"
        },
        {
          "classification": "KNOWN",
          "statement": "API key 不得进入浏览器持久化、URL、日志、analytics、Living Brief、Trace、manifest、git 或真实测试 fixture"
        },
        {
          "classification": "KNOWN",
          "statement": "用户授权必须独立于凭据存在，并在外部 Provider 调用前说明共享内容、接收方和用途"
        },
        {
          "classification": "KNOWN",
          "statement": "MVP 必须支持 390、768、1280 和 1440 代表性视口，键盘操作、清晰标签、焦点、错误关联和 reduced motion"
        },
        {
          "classification": "KNOWN",
          "statement": "生产路径通过同源服务端 typed BrainstormApi 调用固定官方 DeepSeek deepseek-v4-pro；DEEPSEEK_API_KEY 只从服务端环境变量解析。"
        },
        {
          "classification": "KNOWN",
          "statement": "浏览器 bundle、sessionStorage、localStorage、URL、日志、telemetry、manifest、Living Brief、Trace、git 和测试 fixture 均不得包含真实 DeepSeek 凭据。"
        },
        {
          "classification": "KNOWN",
          "statement": "DeepSeek 超时、429、5xx、无效 JSON 或 schema failure 必须返回可恢复且脱敏的错误，不得泄漏响应体、密钥、stack 或内部路径。"
        },
        {
          "classification": "KNOWN",
          "statement": "development mock 仅限 test/development 显式模式，production path 不得回退或伪装成真实 Governor 结果。"
        },
        {
          "classification": "KNOWN",
          "statement": "界面应平静、专业、高信息密度并避免通用 dashboard 和 AI 紫色发光风格"
        },
        {
          "classification": "KNOWN",
          "statement": "不引入超出 MVP 所需的大型状态管理或组件框架"
        }
      ],
      "kill": {
        "classification": "KNOWN",
        "statement": "任一真实调用未经过服务端、密钥或响应体泄漏、任意 URL 可被请求、模型输出未经 schema 验证、非 COMMIT 显示 Final Handoff，或真实 smoke/E2E 未通过"
      },
      "non_goals": [
        {
          "classification": "KNOWN",
          "statement": "本轮不修改 P0–P6 Governor runtime、锁定决定或合法状态语义"
        },
        {
          "classification": "KNOWN",
          "statement": "本轮只接入固定官方 DeepSeek deepseek-v4-pro；不开放任意 Provider URL、不实现真实 multi-provider Council 或生产身份系统"
        },
        {
          "classification": "KNOWN",
          "statement": "本轮不部署、不配置 DNS、不把真实凭据写入仓库或浏览器、不 push、不 merge 或创建 PR"
        }
      ],
      "problem": {
        "classification": "KNOWN",
        "statement": "已验收 Web Host 仍由 development mock 生成结果，尚不能证明真实模型、服务端 canonical state 与 Governor handoff 能端到端运作"
      },
      "success": {
        "classification": "KNOWN",
        "statement": "前后端 typecheck、lint、单元与集成测试、production build、真实 Provider smoke、React/UI/安全审查、P7 validator 和 P0–P6 regression 全部通过。"
      },
      "user": {
        "classification": "KNOWN",
        "statement": "希望把模糊想法转成可验证方向，但不应接触 Governor JSON、CLI 或内部 checkpoint 的产品构建者与小型团队"
      }
    },
    "parallelism": 1,
    "research_allowed": false,
    "result": {
      "cheapest_test": "用已配置 DEEPSEEK_API_KEY 发起一个受限真实 run，验证响应 model/usage、schema、Human Gate evaluator、COMMIT handoff、重启恢复和 secret scan。",
      "confidence": 0.9,
      "exit_status": "COMMIT",
      "recommendation": "c1",
      "shortlist": [
        "c1"
      ]
    },
    "routing_reason": "explicit mode override: Stress",
    "run": {
      "budget": {
        "max_parallelism": 1,
        "max_steps": 64,
        "used_steps": 10
      },
      "id": "brainstorm-web-host-deepseek-v3",
      "mode": "Stress",
      "stage": "EVALUATE",
      "status": "COMPLETED"
    },
    "unknowns": []
  },
  "schema_version": 1,
  "scope_in": [
    "保留已验收 React Web Host、六 Frame、合法状态、NEEDS_INPUT、Human Gate 与 COMMIT-only handoff",
    "新增同源本地 HTTP backend，backend 成为 session 与 Governor workflow truth",
    "固定官方 DeepSeek endpoint、deepseek-v4-pro 和 DEEPSEEK_API_KEY 服务端 secret source",
    "真实模型生成、bounded evaluator、usage receipt、脱敏错误与服务器端非 secret session persistence",
    "真实 Provider smoke、浏览器 E2E、安全审查和 P0–P7 regression"
  ],
  "scope_out": [
    "本轮不修改 P0–P6 Governor runtime、锁定决定或合法状态语义",
    "本轮只接入固定官方 DeepSeek deepseek-v4-pro；不开放任意 Provider URL、不实现真实 multi-provider Council 或生产身份系统",
    "本轮不部署、不配置 DNS、不把真实凭据写入仓库或浏览器、不 push、不 merge 或创建 PR"
  ],
  "status": "COMPLETED",
  "success_metric": "前后端 typecheck、lint、单元与集成测试、production build、真实 Provider smoke、React/UI/安全审查、P7 validator 和 P0–P6 regression 全部通过。",
  "target_user": "希望把模糊想法转成可验证方向，但不应接触 Governor JSON、CLI 或内部 checkpoint 的产品构建者与小型团队",
  "unknowns": [],
  "unvalidated_assumptions": [
    "DeepSeek v4 Pro 可稳定返回满足受限 JSON contract 的候选与评估结果",
    "熟悉 Governor schema 的内部工程用户",
    "用户具备内部 schema 知识",
    "目标用户能够安全理解并编辑 Governor JSON",
    "偏好自由对话而非显式结构的用户",
    "可靠地从自由文本提取全部必填 Frame",
    "隐式 Frame 不会降低可解释性、恢复能力和知识分类准确性",
    "只需要审计既有 run 的 reviewer",
    "所有用户已有由其他入口创建的合法 session",
    "只读审阅足以替代新建和恢复 brainstorm session"
  ],
  "validated_assumptions": []
}
```
<!-- BRAINSTORM_GOVERNOR_STATE_V1_END -->

## Problem

- Problem: 已验收 Web Host 仍由 development mock 生成结果，尚不能证明真实模型、服务端 canonical state 与 Governor handoff 能端到端运作
- Target user: 希望把模糊想法转成可验证方向，但不应接触 Governor JSON、CLI 或内部 checkpoint 的产品构建者与小型团队
- Success metric: 前后端 typecheck、lint、单元与集成测试、production build、真实 Provider smoke、React/UI/安全审查、P7 validator 和 P0–P6 regression 全部通过。
- Kill criterion: 任一真实调用未经过服务端、密钥或响应体泄漏、任意 URL 可被请求、模型输出未经 schema 验证、非 COMMIT 显示 Final Handoff，或真实 smoke/E2E 未通过

## Scope and constraints

- Constraints: Idea stage 只能映射到 Shape、Spark、Stress、Decide 四种现有模式; 六 Frame 必须映射 target_user、core_task、desired_change、hard_constraints、success_metrics、abandonment_criteria、non_goals 和 validation_horizon，并保留知识分类; 运行页必须表达 Governor 阶段、NEEDS_INPUT 恢复、External Capability Gate、Council Enable/Skip、Human Gate 和合法状态; 只有 Governor 返回 COMMIT 时才能展示正式 Final Handoff; API key 不得进入浏览器持久化、URL、日志、analytics、Living Brief、Trace、manifest、git 或真实测试 fixture; 用户授权必须独立于凭据存在，并在外部 Provider 调用前说明共享内容、接收方和用途; MVP 必须支持 390、768、1280 和 1440 代表性视口，键盘操作、清晰标签、焦点、错误关联和 reduced motion; 生产路径通过同源服务端 typed BrainstormApi 调用固定官方 DeepSeek deepseek-v4-pro；DEEPSEEK_API_KEY 只从服务端环境变量解析。; 浏览器 bundle、sessionStorage、localStorage、URL、日志、telemetry、manifest、Living Brief、Trace、git 和测试 fixture 均不得包含真实 DeepSeek 凭据。; DeepSeek 超时、429、5xx、无效 JSON 或 schema failure 必须返回可恢复且脱敏的错误，不得泄漏响应体、密钥、stack 或内部路径。; development mock 仅限 test/development 显式模式，production path 不得回退或伪装成真实 Governor 结果。; 界面应平静、专业、高信息密度并避免通用 dashboard 和 AI 紫色发光风格; 不引入超出 MVP 所需的大型状态管理或组件框架
- Scope in: 保留已验收 React Web Host、六 Frame、合法状态、NEEDS_INPUT、Human Gate 与 COMMIT-only handoff; 新增同源本地 HTTP backend，backend 成为 session 与 Governor workflow truth; 固定官方 DeepSeek endpoint、deepseek-v4-pro 和 DEEPSEEK_API_KEY 服务端 secret source; 真实模型生成、bounded evaluator、usage receipt、脱敏错误与服务器端非 secret session persistence; 真实 Provider smoke、浏览器 E2E、安全审查和 P0–P7 regression
- Scope out: 本轮不修改 P0–P6 Governor runtime、锁定决定或合法状态语义; 本轮只接入固定官方 DeepSeek deepseek-v4-pro；不开放任意 Provider URL、不实现真实 multi-provider Council 或生产身份系统; 本轮不部署、不配置 DNS、不把真实凭据写入仓库或浏览器、不 push、不 merge 或创建 PR

## Locked concept

c1

## Assumptions and unknowns

- Assumptions: DeepSeek v4 Pro 可稳定返回满足受限 JSON contract 的候选与评估结果; 熟悉 Governor schema 的内部工程用户; 用户具备内部 schema 知识; 目标用户能够安全理解并编辑 Governor JSON; 偏好自由对话而非显式结构的用户; 可靠地从自由文本提取全部必填 Frame; 隐式 Frame 不会降低可解释性、恢复能力和知识分类准确性; 只需要审计既有 run 的 reviewer; 所有用户已有由其他入口创建的合法 session; 只读审阅足以替代新建和恢复 brainstorm session
- Unknowns / open questions: —

## Evidence and decisions

- Evidence: 0 record(s)
- Decision log: 0 change(s)

## Risks and next test

- Risks: 模型输出可能不满足 Governor schema，必须在 canonical state 之前验证并安全失败。; Provider 延迟、限流或服务失败可能中断 run，必须有超时、有限重试和幂等 revision。; Prompt injection 可能试图把用户内容变成模型指令，所有输入必须按 DATA_ONLY 处理。; 服务端密钥可能经日志、错误或浏览器 payload 泄漏。; 任意 Provider URL 会形成 SSRF，因此 endpoint 与 model 必须固定并在服务端配置。; 单一 DeepSeek Provider 不能被表述为 multi-provider Council。
- Cheapest test: 用已配置 DEEPSEEK_API_KEY 发起一个受限真实 run，验证响应 model/usage、schema、Human Gate evaluator、COMMIT handoff、重启恢复和 secret scan。
- Exit status: COMMIT

## Resume point

- Stage: EVALUATE
- Status: COMPLETED
- Previous stop reason: COMMIT
- Next action: produce the restricted Brainstorm Web Host handoff
