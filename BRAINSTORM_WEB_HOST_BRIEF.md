# CONCEPT_BRIEF

<!-- BRAINSTORM_GOVERNOR_STATE_V1_START -->
```json
{
  "assumptions": [
    "typed development mock 可以在不伪装真实 Governor 结果的前提下验证完整前端交互",
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
  "cheapest_test": "用 development mock adapter 运行标准路径、NEEDS_INPUT、Council、Provider failure 和刷新恢复五个浏览器场景，并检查密钥未进入持久化或日志。",
  "constraints": [
    "Idea stage 只能映射到 Shape、Spark、Stress、Decide 四种现有模式",
    "六 Frame 必须映射 target_user、core_task、desired_change、hard_constraints、success_metrics、abandonment_criteria、non_goals 和 validation_horizon，并保留知识分类",
    "运行页必须表达 Governor 阶段、NEEDS_INPUT 恢复、External Capability Gate、Council Enable/Skip、Human Gate 和合法状态",
    "只有 Governor 返回 COMMIT 时才能展示正式 Final Handoff",
    "API key 不得进入浏览器持久化、URL、日志、analytics、Living Brief、Trace、manifest、git 或真实测试 fixture",
    "用户授权必须独立于凭据存在，并在外部 Provider 调用前说明共享内容、接收方和用途",
    "MVP 必须支持 390、768、1280 和 1440 代表性视口，键盘操作、清晰标签、焦点、错误关联和 reduced motion",
    "界面应平静、专业、高信息密度并避免通用 dashboard 和 AI 紫色发光风格",
    "不引入超出 MVP 所需的大型状态管理或组件框架"
  ],
  "current_stage": "EVALUATE",
  "decision_log": [],
  "eliminated_candidates": [],
  "evidence": [],
  "exit_status": "COMMIT",
  "kill_criterion": "任一核心流程无法完成、非 COMMIT 显示正式 handoff、密钥进入持久化或日志、刷新丢失非敏感 session 投影，或前端要求用户编辑 Governor JSON",
  "locked_concept": "c1",
  "next_action": "produce the restricted Brainstorm Web Host handoff",
  "open_questions": [],
  "previous_stop_reason": "COMMIT",
  "problem": "现有 Brainstorm Governor 具备完整运行合同，但缺少不暴露 JSON 和 CLI 的浏览器交互层，普通用户无法安全完成从想法输入到最终 handoff 的连续流程",
  "risks": [
    "development mock 与未来真实 backend contract 漂移会造成错误集成信心。",
    "session 恢复实现若边界不清，可能把前端 projection 误当 Governor canonical state。",
    "API key 可能因持久化、日志或错误处理疏漏而泄漏。",
    "单 Provider 或 Provider failure 可能被 UI 错误表述为真实 COUNCIL。",
    "非 COMMIT 状态可能被错误展示为 Final、Approved 或 Ready for implementation。",
    "高密度多阶段流程可能在移动端、键盘或辅助技术下不可完成。"
  ],
  "runtime_state": {
    "assumptions": [
      {
        "classification": "ASSUMPTION",
        "statement": "typed development mock 可以在不伪装真实 Governor 结果的前提下验证完整前端交互"
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
        "complexity": "MEDIUM",
        "core_mechanism": "route-based guided wizard with typed session projection and isolated development mock adapter",
        "exploration_lens": "BASELINE",
        "id": "c1",
        "key_assumptions": [
          {
            "classification": "ASSUMPTION",
            "statement": "typed development mock 可以在不伪装真实 Governor 结果的前提下验证完整前端交互"
          }
        ],
        "main_dependency": {
          "classification": "KNOWN",
          "statement": "浏览器端路由、session projection 和 mock adapter 必须共享同一 typed API contract"
        },
        "one_liner": "以 typed session projection、六 Frame Wizard 和显式 Governor gate 构成完整可恢复前端流程。",
        "target_user": {
          "classification": "KNOWN",
          "statement": "不应接触 Governor JSON 的产品构建者与小型团队"
        },
        "title": "结构化 Wizard Web Host",
        "value_created": "把 Governor 的复杂状态转成可理解、可恢复、可验证的浏览器交互，同时保留后端为唯一 workflow truth。",
        "why_distinct": "明确区分 server canonical、client projection 和 secret ephemeral state，并对每个合法 stop 提供专用 UX。"
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
            "idem:v1:1278bf17eb4b27fb0179e708a469993a2eda9ec230cc5c1d5f2019ef62c76747": 1,
            "idem:v1:19e02cae7f78ef125ddb33d222cb682e5118ece4d78c72d36ba1ac3cac6de0bf": 1,
            "idem:v1:26025f78f22dddc3cb32bf9a853e4a48e1fe61c539c80ef4788a5fb1e6dd2d95": 1,
            "idem:v1:2cd8a96fd8f23c697fefe0f3ac5800e612ea223515b943fed91ca6dbf02373ac": 1,
            "idem:v1:32550e9e606f28e77fc9a195072feaf6bfa57d31c5a604269d442a7164ed5cc6": 1,
            "idem:v1:37c83765347c25b7b4bf80127275cc8aabe612083665a925f32e3b50f8edb969": 1,
            "idem:v1:6ab04f55dd272a3a44be4ee5bb8a3f9d6b9c7964e5dde24e72629edfd4f1755a": 1,
            "idem:v1:b6fb1dcec8835f0c28adb23eb4927da26be56d4843c966b40b9bc558028a298b": 1,
            "idem:v1:ba75c37fe3e1b15457be7075ba714adc741e9ed385718a6359c6594539b046d5": 1,
            "idem:v1:d82c8bd227c0f3cc0ec576f8105f42277426821477ee0a13780b48d83dab0c50": 1
          },
          "evaluator_consumed_keys": [
            "idem:v1:4cfef139386d8ec9ecaa34559b3c984d04806dc24d6d88688ac07731af271952"
          ],
          "evaluator_request_keys": [
            "idem:v1:4cfef139386d8ec9ecaa34559b3c984d04806dc24d6d88688ac07731af271952"
          ],
          "evaluator_rounds_used": 1,
          "failure_ledger": [],
          "idempotency_key": "idem:v1:53d0d5f286d70a596195f281cf5629a0cfdf83bfe05e679e34efd54ad3a46793",
          "in_flight_operation": null,
          "last_completed_stage": "EVALUATE",
          "next_stage": null,
          "operation_receipts": {
            "idem:v1:4cfef139386d8ec9ecaa34559b3c984d04806dc24d6d88688ac07731af271952": {
              "report": {
                "corrections": []
              },
              "runtime_usage": {
                "token_usage": null,
                "tool_usage": null
              }
            }
          },
          "quality_gate_id": "quality:brainstorm-web-host-v1:round-1",
          "recovery_count": 0,
          "revision": 37,
          "run_id": "brainstorm-web-host-v1",
          "schema_version": 1,
          "state_hash": "v1:sha256:0022e2aea06ba8e11497fc03f0e6e6288bddf7cae7c1abe7d2100c14e4fd04c9",
          "trace_cursor": 63,
          "usage_receipt_ids": [
            "usage:v1:sha256:fa5e22ee3bdaadb01cbda4cc2aca69622338d135208332d6839e5ef77cbbc58d"
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
          "statement": "界面应平静、专业、高信息密度并避免通用 dashboard 和 AI 紫色发光风格"
        },
        {
          "classification": "KNOWN",
          "statement": "不引入超出 MVP 所需的大型状态管理或组件框架"
        }
      ],
      "kill": {
        "classification": "KNOWN",
        "statement": "任一核心流程无法完成、非 COMMIT 显示正式 handoff、密钥进入持久化或日志、刷新丢失非敏感 session 投影，或前端要求用户编辑 Governor JSON"
      },
      "non_goals": [
        {
          "classification": "KNOWN",
          "statement": "本轮不修改 P0–P6 Governor runtime、锁定决定或合法状态语义"
        },
        {
          "classification": "KNOWN",
          "statement": "本轮不实现或宣称真实后端编排、真实 Provider 调用和生产身份系统"
        },
        {
          "classification": "KNOWN",
          "statement": "本轮不部署、不配置 DNS、不保存真实凭据、不 push、不 merge 或创建 PR"
        }
      ],
      "problem": {
        "classification": "KNOWN",
        "statement": "现有 Brainstorm Governor 具备完整运行合同，但缺少不暴露 JSON 和 CLI 的浏览器交互层，普通用户无法安全完成从想法输入到最终 handoff 的连续流程"
      },
      "success": {
        "classification": "KNOWN",
        "statement": "标准跳过路径、NEEDS_INPUT 恢复、Council 双 Provider 授权、Provider 失败和刷新恢复均可在浏览器完成；typecheck、lint、行为测试、production build、E2E、无障碍、React 与安全审查全部通过"
      },
      "user": {
        "classification": "KNOWN",
        "statement": "希望把模糊想法转成可验证方向，但不应接触 Governor JSON、CLI 或内部 checkpoint 的产品构建者与小型团队"
      }
    },
    "parallelism": 1,
    "research_allowed": false,
    "result": {
      "cheapest_test": "用 development mock adapter 运行标准路径、NEEDS_INPUT、Council、Provider failure 和刷新恢复五个浏览器场景，并检查密钥未进入持久化或日志。",
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
      "id": "brainstorm-web-host-v1",
      "mode": "Stress",
      "stage": "EVALUATE",
      "status": "COMPLETED"
    },
    "unknowns": []
  },
  "schema_version": 1,
  "scope_in": [
    "Idea Intake 与四种现有 Governor mode 映射",
    "六 Frame Wizard、知识分类、校验与刷新恢复",
    "运行进度、合法状态、NEEDS_INPUT 恢复与 Human Gate",
    "External Capability Gate、Council Enable/Skip、授权和临时密钥处理",
    "COMMIT-only Final Handoff 与开发 mock adapter",
    "响应式、无障碍、自动化测试、浏览器 E2E 和前端安全审查"
  ],
  "scope_out": [
    "本轮不修改 P0–P6 Governor runtime、锁定决定或合法状态语义",
    "本轮不实现或宣称真实后端编排、真实 Provider 调用和生产身份系统",
    "本轮不部署、不配置 DNS、不保存真实凭据、不 push、不 merge 或创建 PR"
  ],
  "status": "COMPLETED",
  "success_metric": "标准跳过路径、NEEDS_INPUT 恢复、Council 双 Provider 授权、Provider 失败和刷新恢复均可在浏览器完成；typecheck、lint、行为测试、production build、E2E、无障碍、React 与安全审查全部通过",
  "target_user": "希望把模糊想法转成可验证方向，但不应接触 Governor JSON、CLI 或内部 checkpoint 的产品构建者与小型团队",
  "unknowns": [],
  "unvalidated_assumptions": [
    "typed development mock 可以在不伪装真实 Governor 结果的前提下验证完整前端交互",
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

- Problem: 现有 Brainstorm Governor 具备完整运行合同，但缺少不暴露 JSON 和 CLI 的浏览器交互层，普通用户无法安全完成从想法输入到最终 handoff 的连续流程
- Target user: 希望把模糊想法转成可验证方向，但不应接触 Governor JSON、CLI 或内部 checkpoint 的产品构建者与小型团队
- Success metric: 标准跳过路径、NEEDS_INPUT 恢复、Council 双 Provider 授权、Provider 失败和刷新恢复均可在浏览器完成；typecheck、lint、行为测试、production build、E2E、无障碍、React 与安全审查全部通过
- Kill criterion: 任一核心流程无法完成、非 COMMIT 显示正式 handoff、密钥进入持久化或日志、刷新丢失非敏感 session 投影，或前端要求用户编辑 Governor JSON

## Scope and constraints

- Constraints: Idea stage 只能映射到 Shape、Spark、Stress、Decide 四种现有模式; 六 Frame 必须映射 target_user、core_task、desired_change、hard_constraints、success_metrics、abandonment_criteria、non_goals 和 validation_horizon，并保留知识分类; 运行页必须表达 Governor 阶段、NEEDS_INPUT 恢复、External Capability Gate、Council Enable/Skip、Human Gate 和合法状态; 只有 Governor 返回 COMMIT 时才能展示正式 Final Handoff; API key 不得进入浏览器持久化、URL、日志、analytics、Living Brief、Trace、manifest、git 或真实测试 fixture; 用户授权必须独立于凭据存在，并在外部 Provider 调用前说明共享内容、接收方和用途; MVP 必须支持 390、768、1280 和 1440 代表性视口，键盘操作、清晰标签、焦点、错误关联和 reduced motion; 界面应平静、专业、高信息密度并避免通用 dashboard 和 AI 紫色发光风格; 不引入超出 MVP 所需的大型状态管理或组件框架
- Scope in: Idea Intake 与四种现有 Governor mode 映射; 六 Frame Wizard、知识分类、校验与刷新恢复; 运行进度、合法状态、NEEDS_INPUT 恢复与 Human Gate; External Capability Gate、Council Enable/Skip、授权和临时密钥处理; COMMIT-only Final Handoff 与开发 mock adapter; 响应式、无障碍、自动化测试、浏览器 E2E 和前端安全审查
- Scope out: 本轮不修改 P0–P6 Governor runtime、锁定决定或合法状态语义; 本轮不实现或宣称真实后端编排、真实 Provider 调用和生产身份系统; 本轮不部署、不配置 DNS、不保存真实凭据、不 push、不 merge 或创建 PR

## Locked concept

c1

## Assumptions and unknowns

- Assumptions: typed development mock 可以在不伪装真实 Governor 结果的前提下验证完整前端交互; 熟悉 Governor schema 的内部工程用户; 用户具备内部 schema 知识; 目标用户能够安全理解并编辑 Governor JSON; 偏好自由对话而非显式结构的用户; 可靠地从自由文本提取全部必填 Frame; 隐式 Frame 不会降低可解释性、恢复能力和知识分类准确性; 只需要审计既有 run 的 reviewer; 所有用户已有由其他入口创建的合法 session; 只读审阅足以替代新建和恢复 brainstorm session
- Unknowns / open questions: —

## Evidence and decisions

- Evidence: 0 record(s)
- Decision log: 0 change(s)

## Risks and next test

- Risks: development mock 与未来真实 backend contract 漂移会造成错误集成信心。; session 恢复实现若边界不清，可能把前端 projection 误当 Governor canonical state。; API key 可能因持久化、日志或错误处理疏漏而泄漏。; 单 Provider 或 Provider failure 可能被 UI 错误表述为真实 COUNCIL。; 非 COMMIT 状态可能被错误展示为 Final、Approved 或 Ready for implementation。; 高密度多阶段流程可能在移动端、键盘或辅助技术下不可完成。
- Cheapest test: 用 development mock adapter 运行标准路径、NEEDS_INPUT、Council、Provider failure 和刷新恢复五个浏览器场景，并检查密钥未进入持久化或日志。
- Exit status: COMMIT

## Resume point

- Stage: EVALUATE
- Status: COMPLETED
- Previous stop reason: COMMIT
- Next action: produce the restricted Brainstorm Web Host handoff
