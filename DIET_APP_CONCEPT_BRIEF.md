# CONCEPT_BRIEF

<!-- BRAINSTORM_GOVERNOR_STATE_V1_START -->
```json
{
  "assumptions": [],
  "cheapest_test": null,
  "constraints": [],
  "current_stage": "FRAME",
  "decision_log": [],
  "eliminated_candidates": [],
  "evidence": [],
  "exit_status": "NEEDS_INPUT",
  "kill_criterion": "kill criterion requires clarification",
  "locked_concept": null,
  "next_action": "provide the missing Problem Frame information",
  "open_questions": [
    "target user requires clarification",
    "job to be done requires clarification",
    "desired change requires clarification",
    "success metric requires clarification",
    "kill criterion requires clarification",
    "time horizon requires clarification"
  ],
  "previous_stop_reason": "NEEDS_INPUT",
  "problem": "请使用 Shape 模式，对一个用于帮助用户控制饮食的 App 进行概念塑形。本轮只讨论产品入口与核心饮食管理功能，不进入技术实现、商业模式、社交功能、运动管理或医疗诊断。\n\n已确认的当前概念：\n1. 产品以 App 作为用户入口。\n2. 提供日历化饮食总结，让用户按日、周、月回顾饮食记录与营养摄入。\n3. 支持拍照识别具体食物，并进一步分析其营养构成。\n4. 提供常规食物列表，支持用户查找并记录常见食物。\n5. 基于用户自身数据，为用户制定营养摄入策略。\n\n本轮 brainstorm 目标：\n- 明确这个功能组合真正解决的用户问题与核心 Job to Be Done。\n- 围绕记录、理解、决策三个环节，形成 2–3 个机制不同、可验证的产品方向。\n- 至少包含一个低复杂度方向，以及一个通过替代或反转现有交互形成的方向。\n- 区分基础记录能力与个性化策略能力，避免把功能清单直接当作产品价值。\n- 对候选方向进行盲点、假设与压力测试，并给出最便宜的验证方式。\n\n当前假设（不得视为已证实事实）：\n- 用户愿意持续记录饮食。\n- 拍照识别能以足够低的操作成本得到可用结果。\n- 日历化总结能帮助用户改变后续饮食决策。\n- 用户愿意提供生成个性化策略所需的身体、目标和饮食数据。\n- 个性化营养策略可以在不构成医疗诊断的边界内提供。\n\n关键未知项：\n- 首要目标用户是谁，以及其核心目标是减脂、增肌、疾病管理、均衡饮食还是其他目标。\n- 用户自身数据具体包含哪些字段，以及哪些字段是必需的。\n- 食物识别、分量估算和营养计算需要达到什么准确度才具有实际价值。\n- 个性化策略是每日摄入目标、餐次建议、实时纠偏，还是其他形式。\n- 用户在记录负担、隐私和建议可信度方面的接受边界。\n\n输出应保留上述未知项，不得擅自补成事实；如果目标用户或成功标准不足以支持收敛，应明确停在 NEEDS_INPUT，并列出最关键的待确认问题。",
  "risks": [],
  "runtime_state": {
    "assumptions": [],
    "candidates": [],
    "decisions": [],
    "deferred": [
      {
        "envelope": {
          "artifact_status": "NONE",
          "budget_charges": {
            "idem:v1:4137f920946e2fe6d519dc8a2afba7b6c416e42c6fca30edf231f3337342d52e": 1,
            "idem:v1:93d88d5578f922914e91e8e18e40dc6b4908d2334bd49270555335bac5e0fac6": 1,
            "idem:v1:96aa5e9185605497edb61833501978821115a691ba3150e50efcce124aae6e0b": 1,
            "idem:v1:d96fe1b0eeda461b1f7a9321934ccda349e88f3968cf8fd3a09798dddcd37ad2": 1
          },
          "evaluator_consumed_keys": [],
          "evaluator_request_keys": [],
          "evaluator_rounds_used": 0,
          "failure_ledger": [],
          "idempotency_key": "idem:v1:cfbb75f16a3931a620a5bfaffb72de7a71e74ce61eaef8246f9913d67a17592c",
          "in_flight_operation": null,
          "last_completed_stage": "FRAME",
          "next_stage": null,
          "operation_receipts": {},
          "quality_gate_id": null,
          "recovery_count": 0,
          "revision": 12,
          "run_id": "diet-control-app-core-v1",
          "schema_version": 1,
          "state_hash": "v1:sha256:3c04a84afbb37b7ec355b6969bb1245ec47de22cec956347224188466b2e02d7",
          "trace_cursor": 21,
          "usage_receipt_ids": [],
          "usage_totals": {}
        },
        "type": "brainstorm-governor-checkpoint-v1"
      }
    ],
    "evidence": [],
    "frame": {
      "constraints": [],
      "kill": {
        "classification": "UNKNOWN",
        "statement": "kill criterion requires clarification"
      },
      "non_goals": [],
      "problem": {
        "classification": "KNOWN",
        "statement": "请使用 Shape 模式，对一个用于帮助用户控制饮食的 App 进行概念塑形。本轮只讨论产品入口与核心饮食管理功能，不进入技术实现、商业模式、社交功能、运动管理或医疗诊断。\n\n已确认的当前概念：\n1. 产品以 App 作为用户入口。\n2. 提供日历化饮食总结，让用户按日、周、月回顾饮食记录与营养摄入。\n3. 支持拍照识别具体食物，并进一步分析其营养构成。\n4. 提供常规食物列表，支持用户查找并记录常见食物。\n5. 基于用户自身数据，为用户制定营养摄入策略。\n\n本轮 brainstorm 目标：\n- 明确这个功能组合真正解决的用户问题与核心 Job to Be Done。\n- 围绕记录、理解、决策三个环节，形成 2–3 个机制不同、可验证的产品方向。\n- 至少包含一个低复杂度方向，以及一个通过替代或反转现有交互形成的方向。\n- 区分基础记录能力与个性化策略能力，避免把功能清单直接当作产品价值。\n- 对候选方向进行盲点、假设与压力测试，并给出最便宜的验证方式。\n\n当前假设（不得视为已证实事实）：\n- 用户愿意持续记录饮食。\n- 拍照识别能以足够低的操作成本得到可用结果。\n- 日历化总结能帮助用户改变后续饮食决策。\n- 用户愿意提供生成个性化策略所需的身体、目标和饮食数据。\n- 个性化营养策略可以在不构成医疗诊断的边界内提供。\n\n关键未知项：\n- 首要目标用户是谁，以及其核心目标是减脂、增肌、疾病管理、均衡饮食还是其他目标。\n- 用户自身数据具体包含哪些字段，以及哪些字段是必需的。\n- 食物识别、分量估算和营养计算需要达到什么准确度才具有实际价值。\n- 个性化策略是每日摄入目标、餐次建议、实时纠偏，还是其他形式。\n- 用户在记录负担、隐私和建议可信度方面的接受边界。\n\n输出应保留上述未知项，不得擅自补成事实；如果目标用户或成功标准不足以支持收敛，应明确停在 NEEDS_INPUT，并列出最关键的待确认问题。"
      },
      "success": {
        "classification": "UNKNOWN",
        "statement": "success metric requires clarification"
      },
      "user": {
        "classification": "UNKNOWN",
        "statement": "target user requires clarification"
      }
    },
    "parallelism": 1,
    "research_allowed": false,
    "result": {
      "cheapest_test": null,
      "confidence": null,
      "exit_status": "NEEDS_INPUT",
      "recommendation": null,
      "shortlist": []
    },
    "routing_reason": "ambiguous concept shaping",
    "run": {
      "budget": {
        "max_parallelism": 1,
        "max_steps": 32,
        "used_steps": 4
      },
      "id": "diet-control-app-core-v1",
      "mode": "Shape",
      "stage": "FRAME",
      "status": "STOPPED"
    },
    "unknowns": [
      {
        "classification": "UNKNOWN",
        "statement": "target user requires clarification"
      },
      {
        "classification": "UNKNOWN",
        "statement": "job to be done requires clarification"
      },
      {
        "classification": "UNKNOWN",
        "statement": "desired change requires clarification"
      },
      {
        "classification": "UNKNOWN",
        "statement": "success metric requires clarification"
      },
      {
        "classification": "UNKNOWN",
        "statement": "kill criterion requires clarification"
      },
      {
        "classification": "UNKNOWN",
        "statement": "time horizon requires clarification"
      }
    ]
  },
  "schema_version": 1,
  "scope_in": [],
  "scope_out": [],
  "status": "STOPPED",
  "success_metric": "success metric requires clarification",
  "target_user": "target user requires clarification",
  "unknowns": [
    "target user requires clarification",
    "job to be done requires clarification",
    "desired change requires clarification",
    "success metric requires clarification",
    "kill criterion requires clarification",
    "time horizon requires clarification"
  ],
  "unvalidated_assumptions": [],
  "validated_assumptions": []
}
```
<!-- BRAINSTORM_GOVERNOR_STATE_V1_END -->

## Problem

- Problem: 请使用 Shape 模式，对一个用于帮助用户控制饮食的 App 进行概念塑形。本轮只讨论产品入口与核心饮食管理功能，不进入技术实现、商业模式、社交功能、运动管理或医疗诊断。  已确认的当前概念： 1. 产品以 App 作为用户入口。 2. 提供日历化饮食总结，让用户按日、周、月回顾饮食记录与营养摄入。 3. 支持拍照识别具体食物，并进一步分析其营养构成。 4. 提供常规食物列表，支持用户查找并记录常见食物。 5. 基于用户自身数据，为用户制定营养摄入策略。  本轮 brainstorm 目标： - 明确这个功能组合真正解决的用户问题与核心 Job to Be Done。 - 围绕记录、理解、决策三个环节，形成 2–3 个机制不同、可验证的产品方向。 - 至少包含一个低复杂度方向，以及一个通过替代或反转现有交互形成的方向。 - 区分基础记录能力与个性化策略能力，避免把功能清单直接当作产品价值。 - 对候选方向进行盲点、假设与压力测试，并给出最便宜的验证方式。  当前假设（不得视为已证实事实）： - 用户愿意持续记录饮食。 - 拍照识别能以足够低的操作成本得到可用结果。 - 日历化总结能帮助用户改变后续饮食决策。 - 用户愿意提供生成个性化策略所需的身体、目标和饮食数据。 - 个性化营养策略可以在不构成医疗诊断的边界内提供。  关键未知项： - 首要目标用户是谁，以及其核心目标是减脂、增肌、疾病管理、均衡饮食还是其他目标。 - 用户自身数据具体包含哪些字段，以及哪些字段是必需的。 - 食物识别、分量估算和营养计算需要达到什么准确度才具有实际价值。 - 个性化策略是每日摄入目标、餐次建议、实时纠偏，还是其他形式。 - 用户在记录负担、隐私和建议可信度方面的接受边界。  输出应保留上述未知项，不得擅自补成事实；如果目标用户或成功标准不足以支持收敛，应明确停在 NEEDS_INPUT，并列出最关键的待确认问题。
- Target user: target user requires clarification
- Success metric: success metric requires clarification
- Kill criterion: kill criterion requires clarification

## Scope and constraints

- Constraints: —
- Scope in: —
- Scope out: —

## Locked concept

—

## Assumptions and unknowns

- Assumptions: —
- Unknowns / open questions: target user requires clarification; job to be done requires clarification; desired change requires clarification; success metric requires clarification; kill criterion requires clarification; time horizon requires clarification

## Evidence and decisions

- Evidence: 0 record(s)
- Decision log: 0 change(s)

## Risks and next test

- Risks: —
- Cheapest test: —
- Exit status: NEEDS_INPUT

## Resume point

- Stage: FRAME
- Status: STOPPED
- Previous stop reason: NEEDS_INPUT
- Next action: provide the missing Problem Frame information
