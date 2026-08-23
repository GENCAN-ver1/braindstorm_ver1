# CONCEPT_BRIEF

<!-- BRAINSTORM_GOVERNOR_STATE_V1_START -->
```json
{
  "assumptions": [
    "静态七日计划已经足以让用户感知个性化价值",
    "用户愿意每天通过食物列表或照片确认执行情况",
    "用户比起查看历史营养数据，更重视下一餐应该怎么吃",
    "实时纠偏建议不会让用户感到被控制或产生挫败感",
    "照片或食物列表输入能够提供足够信息支持当天的方向性调整",
    "隐藏热量数字会提高持续使用意愿，而不会降低用户信任",
    "有限的下一餐选项能够适配上班族真实的外食环境",
    "下一餐行动建议比历史营养总结更能推动用户持续使用",
    "人工辅助生成的方向性建议可以替代首轮原型中的完整自动化能力",
    "减少热量数字展示会提升目标用户的使用粘性"
  ],
  "cheapest_test": "在一周内用可点击原型加人工后台模拟个性化计划、食物识别确认和下一餐纠偏；邀请少量目标用户连续使用七天，观察记录连续性、计划跟随行为，以及相对初始目标的明确正向反馈。首轮不开发完整自动识别或自动营养计算。",
  "constraints": [
    "一周内完成首轮 App 核心功能原型并进入验证",
    "首轮概念必须覆盖日历总结、拍照或食物列表记录，以及个性化计划建议",
    "建议不得越界为医疗诊断或疾病治疗方案",
    "尽量减少用户手动计算和录入热量的负担",
    "产品体验应以行动计划为中心，而不是以营养数据展示为中心"
  ],
  "current_stage": "CONVERGE",
  "decision_log": [],
  "eliminated_candidates": [],
  "evidence": [],
  "exit_status": "NEEDS_INPUT",
  "kill_criterion": "测试用户无法形成持续使用并跟随计划的初步应用粘性",
  "locked_concept": "c2",
  "next_action": "provide the missing Problem Frame information",
  "open_questions": [
    "身体状态良性反馈应使用什么可观察指标定义",
    "应用粘性的最低通过阈值是什么",
    "生成个性化计划所需的最小用户数据集合是什么",
    "食物识别、分量估算与营养计算需要达到什么准确度才足以支持用户决策",
    "生成首版计划所需的最小用户数据和安全规则尚未确定",
    "食物识别、分量估算和建议规则能否在低误导风险下形成闭环尚未验证",
    "如何在不展示详细计算过程的情况下建立建议可信度尚未确定",
    "用户可以容忍计划与临时生活安排之间的偏差",
    "什么程度的建议误差会破坏用户信任尚未确定",
    "用户愿意在看不到详细计算过程时相信下一餐建议"
  ],
  "previous_stop_reason": "NEEDS_INPUT",
  "problem": "希望减脂但不愿手动计算热量的年轻上班族，缺少一个能结合个人身体、生活节奏和饮食习惯，把低负担记录转化为可执行饮食计划的工具",
  "risks": [],
  "runtime_state": {
    "assumptions": [
      {
        "classification": "ASSUMPTION",
        "statement": "静态七日计划已经足以让用户感知个性化价值"
      },
      {
        "classification": "ASSUMPTION",
        "statement": "用户愿意每天通过食物列表或照片确认执行情况"
      },
      {
        "classification": "ASSUMPTION",
        "statement": "用户比起查看历史营养数据，更重视下一餐应该怎么吃"
      },
      {
        "classification": "ASSUMPTION",
        "statement": "实时纠偏建议不会让用户感到被控制或产生挫败感"
      },
      {
        "classification": "ASSUMPTION",
        "statement": "照片或食物列表输入能够提供足够信息支持当天的方向性调整"
      },
      {
        "classification": "ASSUMPTION",
        "statement": "隐藏热量数字会提高持续使用意愿，而不会降低用户信任"
      },
      {
        "classification": "ASSUMPTION",
        "statement": "有限的下一餐选项能够适配上班族真实的外食环境"
      },
      {
        "classification": "ASSUMPTION",
        "statement": "下一餐行动建议比历史营养总结更能推动用户持续使用"
      },
      {
        "classification": "ASSUMPTION",
        "statement": "人工辅助生成的方向性建议可以替代首轮原型中的完整自动化能力"
      },
      {
        "classification": "ASSUMPTION",
        "statement": "减少热量数字展示会提升目标用户的使用粘性"
      }
    ],
    "candidates": [
      {
        "complexity": "LOW",
        "core_mechanism": "static seven-day personalized plan with simplified food confirmation and calendar adherence tracking",
        "exploration_lens": "BASELINE",
        "id": "c1",
        "key_assumptions": [
          {
            "classification": "ASSUMPTION",
            "statement": "静态七日计划已经足以让用户感知个性化价值"
          },
          {
            "classification": "ASSUMPTION",
            "statement": "用户愿意每天通过食物列表或照片确认执行情况"
          }
        ],
        "main_dependency": {
          "classification": "UNKNOWN",
          "statement": "生成首版计划所需的最小用户数据和安全规则尚未确定"
        },
        "one_liner": "先生成一份可执行的七日计划，再用简化记录与日历复盘验证用户是否愿意持续跟随。",
        "target_user": {
          "classification": "KNOWN",
          "statement": "希望减脂但不愿手动计算热量的年轻上班族"
        },
        "title": "七日个性化计划表",
        "value_created": "用低复杂度方式快速交付个性化计划价值，并减少首轮原型对实时算法的依赖。",
        "why_distinct": "计划在周期开始时生成，记录主要用于确认执行情况，不进行实时重算。"
      },
      {
        "complexity": "MEDIUM",
        "core_mechanism": "closed-loop meal logging followed by same-day next-meal plan adjustment",
        "exploration_lens": "ANALOGY",
        "id": "c2",
        "key_assumptions": [
          {
            "classification": "ASSUMPTION",
            "statement": "用户比起查看历史营养数据，更重视下一餐应该怎么吃"
          },
          {
            "classification": "ASSUMPTION",
            "statement": "实时纠偏建议不会让用户感到被控制或产生挫败感"
          },
          {
            "classification": "ASSUMPTION",
            "statement": "照片或食物列表输入能够提供足够信息支持当天的方向性调整"
          }
        ],
        "main_dependency": {
          "classification": "UNKNOWN",
          "statement": "食物识别、分量估算和建议规则能否在低误导风险下形成闭环尚未验证"
        },
        "one_liner": "每次拍照或选择食物后，立即根据当天剩余目标调整下一餐建议。",
        "target_user": {
          "classification": "KNOWN",
          "statement": "希望减脂但不愿手动计算热量的年轻上班族"
        },
        "title": "实时自适应饮食教练",
        "value_created": "把饮食记录直接转化为下一步行动，让用户感知 App 在主动带领计划。",
        "why_distinct": "计划不是固定菜单，而是随着真实饮食行为在当天持续纠偏。"
      },
      {
        "complexity": "MEDIUM",
        "core_mechanism": "replace calorie dashboards with photo check-ins, adherence signals, and constrained next-meal choices",
        "exploration_lens": "SUBSTITUTION",
        "id": "c3",
        "key_assumptions": [
          {
            "classification": "ASSUMPTION",
            "statement": "隐藏热量数字会提高持续使用意愿，而不会降低用户信任"
          },
          {
            "classification": "ASSUMPTION",
            "statement": "有限的下一餐选项能够适配上班族真实的外食环境"
          }
        ],
        "main_dependency": {
          "classification": "UNKNOWN",
          "statement": "如何在不展示详细计算过程的情况下建立建议可信度尚未确定"
        },
        "one_liner": "隐藏复杂营养数字，只通过照片签到、计划完成度和下一餐选项引导用户行动。",
        "target_user": {
          "classification": "KNOWN",
          "statement": "希望减脂但不愿手动计算热量的年轻上班族"
        },
        "title": "无热量界面的下一餐导航",
        "value_created": "降低数字焦虑和学习成本，使用户只需要做少量可执行选择。",
        "why_distinct": "以行为导航替代热量和营养仪表盘，把数据分析隐藏在产品后台。"
      }
    ],
    "decisions": [],
    "deferred": [
      {
        "envelope": {
          "artifact_status": "NONE",
          "budget_charges": {
            "idem:v1:1ddf9c91a50fa6e9c9a6a5aecb88042650e663d57b1d57e472e22c07151d23d2": 1,
            "idem:v1:238143349a899f3ec4f0d66cad4b1cdf1c592c19892b13133312ecae7f66f17a": 1,
            "idem:v1:4b1c1374865cde49055c28cdd68ea1ed9dffe23d5b5e62c9ef9209f5b221d64a": 1,
            "idem:v1:4c0c1ec8535cba13a409be6e83e660cba274395cc94cdc2c557938410d44d15c": 1,
            "idem:v1:4efd92464daccca2b3a2d84ffe2ea6c016354e1f0de51b13dc0361345758e7ee": 1,
            "idem:v1:524babd1661bfeabecc02e8435d02b3a0a7bb302bf9272e83bbf792b7d6e5d9e": 1,
            "idem:v1:a522266c6a6b9babe21948223bc445e89d03b58a243092ea99d5c756516f38bd": 1,
            "idem:v1:db60350a9af2c0ed3481351b4f7e09d0c48ca4dbfe44f627b475b7162476483a": 1
          },
          "evaluator_consumed_keys": [],
          "evaluator_request_keys": [],
          "evaluator_rounds_used": 0,
          "failure_ledger": [],
          "idempotency_key": "idem:v1:efbab1b6f454072e005a07c83bc1c3454532b2d648c58814c46573b6e6dc57c2",
          "in_flight_operation": null,
          "last_completed_stage": "CONVERGE",
          "next_stage": null,
          "operation_receipts": {},
          "quality_gate_id": null,
          "recovery_count": 0,
          "revision": 24,
          "run_id": "diet-control-app-core-v2",
          "schema_version": 1,
          "state_hash": "v1:sha256:245594f8bcedf269555ad9137fa3093dd2d4d19d8d1484a1f953c2bcd6cef7ba",
          "trace_cursor": 41,
          "usage_receipt_ids": [],
          "usage_totals": {}
        },
        "type": "brainstorm-governor-checkpoint-v1"
      }
    ],
    "evidence": [],
    "frame": {
      "constraints": [
        {
          "classification": "KNOWN",
          "statement": "一周内完成首轮 App 核心功能原型并进入验证"
        },
        {
          "classification": "KNOWN",
          "statement": "首轮概念必须覆盖日历总结、拍照或食物列表记录，以及个性化计划建议"
        },
        {
          "classification": "KNOWN",
          "statement": "建议不得越界为医疗诊断或疾病治疗方案"
        },
        {
          "classification": "KNOWN",
          "statement": "尽量减少用户手动计算和录入热量的负担"
        },
        {
          "classification": "KNOWN",
          "statement": "产品体验应以行动计划为中心，而不是以营养数据展示为中心"
        }
      ],
      "kill": {
        "classification": "KNOWN",
        "statement": "测试用户无法形成持续使用并跟随计划的初步应用粘性"
      },
      "non_goals": [
        {
          "classification": "KNOWN",
          "statement": "本轮不制定完整技术架构或工程实施计划"
        },
        {
          "classification": "KNOWN",
          "statement": "本轮不讨论商业模式、社交功能或运动管理"
        },
        {
          "classification": "KNOWN",
          "statement": "本产品不提供医疗诊断或疾病治疗"
        }
      ],
      "problem": {
        "classification": "KNOWN",
        "statement": "希望减脂但不愿手动计算热量的年轻上班族，缺少一个能结合个人身体、生活节奏和饮食习惯，把低负担记录转化为可执行饮食计划的工具"
      },
      "success": {
        "classification": "KNOWN",
        "statement": "测试用户连续记录七天，并相对其初始目标报告至少一种明确的身体状态或行为层面的正向反馈"
      },
      "user": {
        "classification": "KNOWN",
        "statement": "希望减脂但不愿手动计算热量的年轻上班族"
      }
    },
    "parallelism": 1,
    "research_allowed": false,
    "result": {
      "cheapest_test": "在一周内用可点击原型加人工后台模拟个性化计划、食物识别确认和下一餐纠偏；邀请少量目标用户连续使用七天，观察记录连续性、计划跟随行为，以及相对初始目标的明确正向反馈。首轮不开发完整自动识别或自动营养计算。",
      "confidence": 0.58,
      "exit_status": "NEEDS_INPUT",
      "recommendation": "c2",
      "shortlist": [
        "c2",
        "c3",
        "c1"
      ]
    },
    "routing_reason": "ambiguous concept shaping",
    "run": {
      "budget": {
        "max_parallelism": 1,
        "max_steps": 32,
        "used_steps": 8
      },
      "id": "diet-control-app-core-v2",
      "mode": "Shape",
      "stage": "CONVERGE",
      "status": "STOPPED"
    },
    "unknowns": [
      {
        "classification": "UNKNOWN",
        "statement": "身体状态良性反馈应使用什么可观察指标定义"
      },
      {
        "classification": "UNKNOWN",
        "statement": "应用粘性的最低通过阈值是什么"
      },
      {
        "classification": "UNKNOWN",
        "statement": "生成个性化计划所需的最小用户数据集合是什么"
      },
      {
        "classification": "UNKNOWN",
        "statement": "食物识别、分量估算与营养计算需要达到什么准确度才足以支持用户决策"
      },
      {
        "classification": "UNKNOWN",
        "statement": "生成首版计划所需的最小用户数据和安全规则尚未确定"
      },
      {
        "classification": "UNKNOWN",
        "statement": "食物识别、分量估算和建议规则能否在低误导风险下形成闭环尚未验证"
      },
      {
        "classification": "UNKNOWN",
        "statement": "如何在不展示详细计算过程的情况下建立建议可信度尚未确定"
      },
      {
        "classification": "UNKNOWN",
        "statement": "用户可以容忍计划与临时生活安排之间的偏差"
      },
      {
        "classification": "UNKNOWN",
        "statement": "什么程度的建议误差会破坏用户信任尚未确定"
      },
      {
        "classification": "UNKNOWN",
        "statement": "用户愿意在看不到详细计算过程时相信下一餐建议"
      }
    ]
  },
  "schema_version": 1,
  "scope_in": [],
  "scope_out": [],
  "status": "STOPPED",
  "success_metric": "测试用户连续记录七天，并相对其初始目标报告至少一种明确的身体状态或行为层面的正向反馈",
  "target_user": "希望减脂但不愿手动计算热量的年轻上班族",
  "unknowns": [
    "身体状态良性反馈应使用什么可观察指标定义",
    "应用粘性的最低通过阈值是什么",
    "生成个性化计划所需的最小用户数据集合是什么",
    "食物识别、分量估算与营养计算需要达到什么准确度才足以支持用户决策",
    "生成首版计划所需的最小用户数据和安全规则尚未确定",
    "食物识别、分量估算和建议规则能否在低误导风险下形成闭环尚未验证",
    "如何在不展示详细计算过程的情况下建立建议可信度尚未确定",
    "用户可以容忍计划与临时生活安排之间的偏差",
    "什么程度的建议误差会破坏用户信任尚未确定",
    "用户愿意在看不到详细计算过程时相信下一餐建议"
  ],
  "unvalidated_assumptions": [
    "静态七日计划已经足以让用户感知个性化价值",
    "用户愿意每天通过食物列表或照片确认执行情况",
    "用户比起查看历史营养数据，更重视下一餐应该怎么吃",
    "实时纠偏建议不会让用户感到被控制或产生挫败感",
    "照片或食物列表输入能够提供足够信息支持当天的方向性调整",
    "隐藏热量数字会提高持续使用意愿，而不会降低用户信任",
    "有限的下一餐选项能够适配上班族真实的外食环境",
    "下一餐行动建议比历史营养总结更能推动用户持续使用",
    "人工辅助生成的方向性建议可以替代首轮原型中的完整自动化能力",
    "减少热量数字展示会提升目标用户的使用粘性"
  ],
  "validated_assumptions": []
}
```
<!-- BRAINSTORM_GOVERNOR_STATE_V1_END -->

## Problem

- Problem: 希望减脂但不愿手动计算热量的年轻上班族，缺少一个能结合个人身体、生活节奏和饮食习惯，把低负担记录转化为可执行饮食计划的工具
- Target user: 希望减脂但不愿手动计算热量的年轻上班族
- Success metric: 测试用户连续记录七天，并相对其初始目标报告至少一种明确的身体状态或行为层面的正向反馈
- Kill criterion: 测试用户无法形成持续使用并跟随计划的初步应用粘性

## Scope and constraints

- Constraints: 一周内完成首轮 App 核心功能原型并进入验证; 首轮概念必须覆盖日历总结、拍照或食物列表记录，以及个性化计划建议; 建议不得越界为医疗诊断或疾病治疗方案; 尽量减少用户手动计算和录入热量的负担; 产品体验应以行动计划为中心，而不是以营养数据展示为中心
- Scope in: —
- Scope out: —

## Locked concept

c2

## Assumptions and unknowns

- Assumptions: 静态七日计划已经足以让用户感知个性化价值; 用户愿意每天通过食物列表或照片确认执行情况; 用户比起查看历史营养数据，更重视下一餐应该怎么吃; 实时纠偏建议不会让用户感到被控制或产生挫败感; 照片或食物列表输入能够提供足够信息支持当天的方向性调整; 隐藏热量数字会提高持续使用意愿，而不会降低用户信任; 有限的下一餐选项能够适配上班族真实的外食环境; 下一餐行动建议比历史营养总结更能推动用户持续使用; 人工辅助生成的方向性建议可以替代首轮原型中的完整自动化能力; 减少热量数字展示会提升目标用户的使用粘性
- Unknowns / open questions: 身体状态良性反馈应使用什么可观察指标定义; 应用粘性的最低通过阈值是什么; 生成个性化计划所需的最小用户数据集合是什么; 食物识别、分量估算与营养计算需要达到什么准确度才足以支持用户决策; 生成首版计划所需的最小用户数据和安全规则尚未确定; 食物识别、分量估算和建议规则能否在低误导风险下形成闭环尚未验证; 如何在不展示详细计算过程的情况下建立建议可信度尚未确定; 用户可以容忍计划与临时生活安排之间的偏差; 什么程度的建议误差会破坏用户信任尚未确定; 用户愿意在看不到详细计算过程时相信下一餐建议

## Evidence and decisions

- Evidence: 0 record(s)
- Decision log: 0 change(s)

## Risks and next test

- Risks: —
- Cheapest test: 在一周内用可点击原型加人工后台模拟个性化计划、食物识别确认和下一餐纠偏；邀请少量目标用户连续使用七天，观察记录连续性、计划跟随行为，以及相对初始目标的明确正向反馈。首轮不开发完整自动识别或自动营养计算。
- Exit status: NEEDS_INPUT

## Resume point

- Stage: CONVERGE
- Status: STOPPED
- Previous stop reason: NEEDS_INPUT
- Next action: provide the missing Problem Frame information
