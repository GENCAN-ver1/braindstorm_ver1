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
  "cheapest_test": "招募目标 8-12 名、最低 8 名目标用户，连续七天使用可点击原型与透明标注的人工后台；用户记录后确认食物和标准份量，后台 10 分钟内返回方向性下一餐建议。主要检验决策成本、继续使用意愿、建议跟随率和确认完成率，并以焦虑/被控制感、响应延迟和医疗越界作为安全失败信号；身体与精神状态变化仅作探索性自报记录。",
  "constraints": [
    "一周内完成首轮 App 核心功能原型并进入验证",
    "首轮概念必须覆盖日历总结、拍照或食物列表记录，以及个性化计划建议",
    "建议不得越界为医疗诊断或疾病治疗方案",
    "尽量减少用户手动计算和录入热量的负担",
    "产品体验应以行动计划为中心，而不是以营养数据展示为中心"
  ],
  "current_stage": "EVALUATE",
  "decision_log": [],
  "eliminated_candidates": [],
  "evidence": [
    {
      "claim": "基础个人信息驱动的个性化建议可能改善饮食行为，但更复杂的表型和基因信息未显示额外效果。",
      "classification": "KNOWN",
      "id": "e1-personalization-can-change-diet",
      "metadata": {
        "contradictions": [],
        "evidence_strength": "HIGH",
        "treatment": "DATA_ONLY"
      },
      "source": "https://pubmed.ncbi.nlm.nih.gov/27524815/"
    },
    {
      "claim": "个性化本身不能被视为效果保证。",
      "classification": "ASSUMPTION",
      "id": "e2-personalization-not-automatically-superior",
      "metadata": {
        "contradictions": [],
        "evidence_strength": "HIGH",
        "treatment": "DATA_ONLY"
      },
      "source": "https://pubmed.ncbi.nlm.nih.gov/36169954/"
    },
    {
      "claim": "图像式分量估算存在测量误差，产品闭环应允许用户确认或修正。",
      "classification": "ASSUMPTION",
      "id": "e3-photo-portions-need-confirmation",
      "metadata": {
        "contradictions": [],
        "evidence_strength": "MEDIUM",
        "treatment": "DATA_ONLY"
      },
      "source": "https://pubmed.ncbi.nlm.nih.gov/33761165/"
    },
    {
      "claim": "一周原型更适合验证记录、计划跟随和决策成本，不适合宣称稳定身体改善。",
      "classification": "ASSUMPTION",
      "id": "e4-one-week-is-behavior-test",
      "metadata": {
        "contradictions": [],
        "evidence_strength": "MEDIUM",
        "treatment": "DATA_ONLY"
      },
      "source": "https://pubmed.ncbi.nlm.nih.gov/41490780/"
    },
    {
      "claim": "照片识别、目标计划和动态营养目标已被现有产品分别覆盖，功能组合本身不足以构成差异化。",
      "classification": "ASSUMPTION",
      "id": "e5-current-competitor-overlap",
      "metadata": {
        "contradictions": [],
        "evidence_strength": "MEDIUM",
        "treatment": "DATA_ONLY"
      },
      "source": "https://support.myfitnesspal.com/hc/en-us/articles/360045761612-Meal-Scan-FAQ | https://help.lifesum.com/en/article/what-do-i-get-when-i-buy-premium-1vzq8pz/ | https://help.macrofactorapp.com/macro_program/program_styles/"
    },
    {
      "claim": "DeepSeek 与 Kimi 独立评审均建议保留 c2 但收缩首周范围，加入人工复核、用户确认、非医疗边界和行为验证护栏。",
      "classification": "ASSUMPTION",
      "id": "council-c2-refine-consensus",
      "metadata": {
        "council_label": "COUNCIL",
        "treatment": "DATA_ONLY"
      },
      "source": "evidence/diet-app-council-synthesis.json"
    }
  ],
  "exit_status": "COMMIT",
  "kill_criterion": "试用结束后，用户既未表现继续使用意愿，也未报告 App 帮助其降低饮食决策成本",
  "locked_concept": "c2",
  "next_action": "produce the restricted approved handoff",
  "open_questions": [
    "不同用户目标应如何选择安全且可比较的一周阶段指标",
    "生成个性化计划所需的最小用户数据集合是什么",
    "食物识别、分量估算与营养计算需要达到什么准确度才足以支持用户决策",
    "生成首版计划所需的最小用户数据和安全规则尚未确定",
    "食物识别、分量估算和建议规则能否在低误导风险下形成闭环尚未验证",
    "如何在不展示详细计算过程的情况下建立建议可信度尚未确定",
    "用户可以容忍计划与临时生活安排之间的偏差",
    "什么程度的建议误差会破坏用户信任尚未确定",
    "用户愿意在看不到详细计算过程时相信下一餐建议"
  ],
  "previous_stop_reason": "COMMIT",
  "problem": "希望改善体重、身体能力或日常精力与主观精神状态，但不愿手动计算热量与营养的年轻上班族，缺少一个能结合个人基线、目标、生活节奏和饮食习惯，把低负担记录转化为下一餐行动的工具",
  "risks": [
    "食物或分量输入错误可能在闭环中放大并破坏信任。",
    "高频纠偏可能带来被控制感、饮食焦虑或通知疲劳。",
    "首周人工响应延迟可能使下一餐建议失去时效性。",
    "功能与现有照片记录、计划和目标更新产品重叠，差异化仍需用户验证。",
    "方向性建议仍可能被用户误解为医疗或健康效果承诺。"
  ],
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
        "exploration_lens": "INVERSION",
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
          "statement": "希望改善体重、身体能力或日常精力与主观精神状态，但不愿手动计算热量与营养的年轻上班族"
        },
        "title": "七日个性化计划表",
        "value_created": "用低复杂度方式快速交付个性化计划价值，并减少首轮原型对实时算法的依赖。",
        "why_distinct": "计划在周期开始时生成，记录主要用于确认执行情况，不进行实时重算。"
      },
      {
        "complexity": "MEDIUM",
        "core_mechanism": "closed-loop meal logging followed by same-day next-meal plan adjustment",
        "exploration_lens": "BASELINE",
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
          "statement": "希望改善体重、身体能力或日常精力与主观精神状态，但不愿手动计算热量与营养的年轻上班族"
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
          "statement": "希望改善体重、身体能力或日常精力与主观精神状态，但不愿手动计算热量与营养的年轻上班族"
        },
        "title": "无热量界面的下一餐导航",
        "value_created": "降低数字焦虑和学习成本，使用户只需要做少量可执行选择。",
        "why_distinct": "以行为导航替代热量和营养仪表盘，把数据分析隐藏在产品后台。"
      }
    ],
    "decisions": [
      {
        "id": "human-gate-c2",
        "rationale": "用户明确确认 c2；Council 只收缩原型边界和验证方式，不改变方向。",
        "status": "LOCKED",
        "topic": "concept",
        "value": "c2"
      }
    ],
    "deferred": [
      {
        "envelope": {
          "artifact_status": "APPROVED",
          "budget_charges": {
            "idem:v1:0f5d6ea56a0222c62e7261e0f277784eeef3b58c5c78dbbad148f3d8c4445bf3": 1,
            "idem:v1:1c3d2d5667a55e938407ee4770d6fd86a826cc80c3aa765a36a2863deef9aadf": 1,
            "idem:v1:3c39d71c0aac04e5f9b263579035b1bd80d852fee6afa02eb569a63d60c5dd5e": 1,
            "idem:v1:3f8f0f374f60bb2af65a095af926d2d66af3619accf01f0da6f9d6f7bcc4c003": 1,
            "idem:v1:5149a9419f8e01f33b53a1195b9c7b61408a19eafca2e9c6145d17f595183810": 1,
            "idem:v1:6527ec3d774dc46fa3929e18753d9fcfe56e046850e457c306c3c1e5ab3c201b": 1,
            "idem:v1:8e31c974de47e645f4cd5800e228b4b0699ce6b9de68344f5ed83900522599e3": 1,
            "idem:v1:a30f4feb81fc8790e350704b12166711ba0a3a3fde6678300473d6e38397b445": 1,
            "idem:v1:b394ad62c35238b3a8175ef488fac0c5c8c812bacbfa62965398723b2f7da78c": 1,
            "idem:v1:f681e9a7a261b17d72c3aa706a27235d905a50c578d016697d8de4073ffbea74": 1
          },
          "evaluator_consumed_keys": [
            "idem:v1:44c8e239dec95d0134491b44178f765bc0af5e8fc9cf6388440a24a491b3a922"
          ],
          "evaluator_request_keys": [
            "idem:v1:44c8e239dec95d0134491b44178f765bc0af5e8fc9cf6388440a24a491b3a922"
          ],
          "evaluator_rounds_used": 1,
          "failure_ledger": [],
          "idempotency_key": "idem:v1:7ce8477948fbb321772108747564da73f9485fa0cb9b807ddf4be8c1e6d635b2",
          "in_flight_operation": null,
          "last_completed_stage": "EVALUATE",
          "next_stage": null,
          "operation_receipts": {
            "idem:v1:44c8e239dec95d0134491b44178f765bc0af5e8fc9cf6388440a24a491b3a922": {
              "report": {
                "corrections": []
              },
              "runtime_usage": {
                "token_usage": 2525,
                "tool_usage": null
              }
            }
          },
          "quality_gate_id": "quality:diet-control-app-core-v3:round-1",
          "recovery_count": 0,
          "revision": 41,
          "run_id": "diet-control-app-core-v3",
          "schema_version": 1,
          "state_hash": "v1:sha256:3de6346620d1b139fee1e444f4f96591feeae134830c9141bfa63ef55de58ca9",
          "trace_cursor": 71,
          "usage_receipt_ids": [
            "usage:v1:sha256:922008a815b8e18251b7044cbabfee26b35b3bd9544f977a685f9886c027afad"
          ],
          "usage_totals": {
            "cached_tokens": 0,
            "completion_tokens": 1,
            "prompt_tokens": 2524,
            "unpriced_calls": 1
          }
        },
        "type": "brainstorm-governor-checkpoint-v1"
      }
    ],
    "evidence": [
      {
        "claim": "基础个人信息驱动的个性化建议可能改善饮食行为，但更复杂的表型和基因信息未显示额外效果。",
        "classification": "KNOWN",
        "id": "e1-personalization-can-change-diet",
        "metadata": {
          "contradictions": [],
          "evidence_strength": "HIGH",
          "treatment": "DATA_ONLY"
        },
        "source": "https://pubmed.ncbi.nlm.nih.gov/27524815/"
      },
      {
        "claim": "个性化本身不能被视为效果保证。",
        "classification": "ASSUMPTION",
        "id": "e2-personalization-not-automatically-superior",
        "metadata": {
          "contradictions": [],
          "evidence_strength": "HIGH",
          "treatment": "DATA_ONLY"
        },
        "source": "https://pubmed.ncbi.nlm.nih.gov/36169954/"
      },
      {
        "claim": "图像式分量估算存在测量误差，产品闭环应允许用户确认或修正。",
        "classification": "ASSUMPTION",
        "id": "e3-photo-portions-need-confirmation",
        "metadata": {
          "contradictions": [],
          "evidence_strength": "MEDIUM",
          "treatment": "DATA_ONLY"
        },
        "source": "https://pubmed.ncbi.nlm.nih.gov/33761165/"
      },
      {
        "claim": "一周原型更适合验证记录、计划跟随和决策成本，不适合宣称稳定身体改善。",
        "classification": "ASSUMPTION",
        "id": "e4-one-week-is-behavior-test",
        "metadata": {
          "contradictions": [],
          "evidence_strength": "MEDIUM",
          "treatment": "DATA_ONLY"
        },
        "source": "https://pubmed.ncbi.nlm.nih.gov/41490780/"
      },
      {
        "claim": "照片识别、目标计划和动态营养目标已被现有产品分别覆盖，功能组合本身不足以构成差异化。",
        "classification": "ASSUMPTION",
        "id": "e5-current-competitor-overlap",
        "metadata": {
          "contradictions": [],
          "evidence_strength": "MEDIUM",
          "treatment": "DATA_ONLY"
        },
        "source": "https://support.myfitnesspal.com/hc/en-us/articles/360045761612-Meal-Scan-FAQ | https://help.lifesum.com/en/article/what-do-i-get-when-i-buy-premium-1vzq8pz/ | https://help.macrofactorapp.com/macro_program/program_styles/"
      },
      {
        "claim": "DeepSeek 与 Kimi 独立评审均建议保留 c2 但收缩首周范围，加入人工复核、用户确认、非医疗边界和行为验证护栏。",
        "classification": "ASSUMPTION",
        "id": "council-c2-refine-consensus",
        "metadata": {
          "council_label": "COUNCIL",
          "treatment": "DATA_ONLY"
        },
        "source": "evidence/diet-app-council-synthesis.json"
      }
    ],
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
        "statement": "试用结束后，用户既未表现继续使用意愿，也未报告 App 帮助其降低饮食决策成本"
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
        "statement": "希望改善体重、身体能力或日常精力与主观精神状态，但不愿手动计算热量与营养的年轻上班族，缺少一个能结合个人基线、目标、生活节奏和饮食习惯，把低负担记录转化为下一餐行动的工具"
      },
      "success": {
        "classification": "KNOWN",
        "statement": "测试用户连续使用七天后，相对初始化现状更接近至少一个自定义目标，或在体重、身体能力、日常精力、主观精神状态或饮食行为中的至少一个维度报告明确改善"
      },
      "user": {
        "classification": "KNOWN",
        "statement": "希望改善体重、身体能力或日常精力与主观精神状态，但不愿手动计算热量与营养的年轻上班族"
      }
    },
    "parallelism": 2,
    "research_allowed": true,
    "result": {
      "cheapest_test": "招募目标 8-12 名、最低 8 名目标用户，连续七天使用可点击原型与透明标注的人工后台；用户记录后确认食物和标准份量，后台 10 分钟内返回方向性下一餐建议。主要检验决策成本、继续使用意愿、建议跟随率和确认完成率，并以焦虑/被控制感、响应延迟和医疗越界作为安全失败信号；身体与精神状态变化仅作探索性自报记录。",
      "confidence": 0.58,
      "exit_status": "COMMIT",
      "recommendation": "c2",
      "shortlist": [
        "c2",
        "c3",
        "c1"
      ]
    },
    "routing_reason": "existing solution plus validation request",
    "run": {
      "budget": {
        "max_parallelism": 2,
        "max_steps": 64,
        "used_steps": 10
      },
      "id": "diet-control-app-core-v3",
      "mode": "Stress",
      "stage": "EVALUATE",
      "status": "COMPLETED"
    },
    "unknowns": [
      {
        "classification": "UNKNOWN",
        "statement": "不同用户目标应如何选择安全且可比较的一周阶段指标"
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
  "scope_in": [
    "初始化目标、主观基线、作息、外食频率、偏好、过敏或禁忌",
    "拍照或食物列表记录与用户分量确认",
    "人工后台生成方向性下一餐建议",
    "用户可控通知、异常场景降级和日历行为复盘",
    "七天 Wizard-of-Oz 行为与决策成本验证"
  ],
  "scope_out": [
    "全自动食物识别与精确营养计算",
    "医疗诊断、疾病管理或治疗建议",
    "用七天结果宣称稳定身体或精神健康改善",
    "商业模式、社交功能、运动管理和完整工程架构"
  ],
  "status": "COMPLETED",
  "success_metric": "测试用户连续使用七天后，相对初始化现状更接近至少一个自定义目标，或在体重、身体能力、日常精力、主观精神状态或饮食行为中的至少一个维度报告明确改善",
  "target_user": "希望改善体重、身体能力或日常精力与主观精神状态，但不愿手动计算热量与营养的年轻上班族",
  "unknowns": [
    "不同用户目标应如何选择安全且可比较的一周阶段指标",
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

- Problem: 希望改善体重、身体能力或日常精力与主观精神状态，但不愿手动计算热量与营养的年轻上班族，缺少一个能结合个人基线、目标、生活节奏和饮食习惯，把低负担记录转化为下一餐行动的工具
- Target user: 希望改善体重、身体能力或日常精力与主观精神状态，但不愿手动计算热量与营养的年轻上班族
- Success metric: 测试用户连续使用七天后，相对初始化现状更接近至少一个自定义目标，或在体重、身体能力、日常精力、主观精神状态或饮食行为中的至少一个维度报告明确改善
- Kill criterion: 试用结束后，用户既未表现继续使用意愿，也未报告 App 帮助其降低饮食决策成本

## Scope and constraints

- Constraints: 一周内完成首轮 App 核心功能原型并进入验证; 首轮概念必须覆盖日历总结、拍照或食物列表记录，以及个性化计划建议; 建议不得越界为医疗诊断或疾病治疗方案; 尽量减少用户手动计算和录入热量的负担; 产品体验应以行动计划为中心，而不是以营养数据展示为中心
- Scope in: 初始化目标、主观基线、作息、外食频率、偏好、过敏或禁忌; 拍照或食物列表记录与用户分量确认; 人工后台生成方向性下一餐建议; 用户可控通知、异常场景降级和日历行为复盘; 七天 Wizard-of-Oz 行为与决策成本验证
- Scope out: 全自动食物识别与精确营养计算; 医疗诊断、疾病管理或治疗建议; 用七天结果宣称稳定身体或精神健康改善; 商业模式、社交功能、运动管理和完整工程架构

## Locked concept

c2

## Assumptions and unknowns

- Assumptions: 静态七日计划已经足以让用户感知个性化价值; 用户愿意每天通过食物列表或照片确认执行情况; 用户比起查看历史营养数据，更重视下一餐应该怎么吃; 实时纠偏建议不会让用户感到被控制或产生挫败感; 照片或食物列表输入能够提供足够信息支持当天的方向性调整; 隐藏热量数字会提高持续使用意愿，而不会降低用户信任; 有限的下一餐选项能够适配上班族真实的外食环境; 下一餐行动建议比历史营养总结更能推动用户持续使用; 人工辅助生成的方向性建议可以替代首轮原型中的完整自动化能力; 减少热量数字展示会提升目标用户的使用粘性
- Unknowns / open questions: 不同用户目标应如何选择安全且可比较的一周阶段指标; 生成个性化计划所需的最小用户数据集合是什么; 食物识别、分量估算与营养计算需要达到什么准确度才足以支持用户决策; 生成首版计划所需的最小用户数据和安全规则尚未确定; 食物识别、分量估算和建议规则能否在低误导风险下形成闭环尚未验证; 如何在不展示详细计算过程的情况下建立建议可信度尚未确定; 用户可以容忍计划与临时生活安排之间的偏差; 什么程度的建议误差会破坏用户信任尚未确定; 用户愿意在看不到详细计算过程时相信下一餐建议

## Evidence and decisions

- Evidence: 6 record(s)
- Decision log: 0 change(s)

## Risks and next test

- Risks: 食物或分量输入错误可能在闭环中放大并破坏信任。; 高频纠偏可能带来被控制感、饮食焦虑或通知疲劳。; 首周人工响应延迟可能使下一餐建议失去时效性。; 功能与现有照片记录、计划和目标更新产品重叠，差异化仍需用户验证。; 方向性建议仍可能被用户误解为医疗或健康效果承诺。
- Cheapest test: 招募目标 8-12 名、最低 8 名目标用户，连续七天使用可点击原型与透明标注的人工后台；用户记录后确认食物和标准份量，后台 10 分钟内返回方向性下一餐建议。主要检验决策成本、继续使用意愿、建议跟随率和确认完成率，并以焦虑/被控制感、响应延迟和医疗越界作为安全失败信号；身体与精神状态变化仅作探索性自报记录。
- Exit status: COMMIT

## Resume point

- Stage: EVALUATE
- Status: COMPLETED
- Previous stop reason: COMMIT
- Next action: produce the restricted approved handoff
