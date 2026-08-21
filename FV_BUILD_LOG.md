# Brainstorm Governor FV 搭建日志

## 结论 / TL;DR

FV-00～FV-08 已按顺序完成。当前版本通过 AC-01～AC-08、P0～P6 `108/108`、项目级 `90/90`、live local regression `16/16` 和整体 Agent smoke `6/6`，发布报告状态为 `FULL_VERSION / PASS`。

这里的 `FULL_VERSION` 指本地运行、安全与发布合同完整，不包含真实 Research、Worker、Evaluator 或 Council Provider 的部署接入。

## FV 操作记录

| 模块 | 主要操作与产物 | 阶段性验证 |
|---|---|---|
| FV-00 | 冻结 AC-01～AC-08；建立 manifest、阶段/故障矩阵、fault injector、状态 fingerprint 和验收骨架 | `23/23` |
| FV-01 | 建立严格统一配置、`FullCycleRunner` 和 `scripts/brainstorm.py run` 单命令入口 | `33/33` |
| FV-02 | 增加每阶段 checkpoint、Brief revision/CAS、状态 hash、in-flight receipt、幂等 re-entry 与迁移 | `44/44` |
| FV-03 | 在阶段工作和外调前统一 Budget Guard；预算耗尽原子保存合法 `PARK` | `54/54` |
| FV-04 | Research/Worker staging、深快照、copy-on-write、operation receipt 与 append-only failure ledger | `66/66` |
| FV-05 | 自动 Event Sink、P4/P5/P6 activation、Provider usage receipt、版本化价格和 Trace/checkpoint 关联 | `74/74` |
| FV-06 | 跨恢复 Evaluator 两轮硬上限；Artifact Writer、manifest/hash 和 restricted Handoff Gate | `82/82` |
| FV-07 | 八维版本指纹、16 场景 live local runner、显式 baseline 审批和 CI regression gate | `88/88` |
| FV-08 | clean-room 单命令、八项 AC 汇总、P0～P6/版本/Skill 门禁、证据 hash 和 Full Version 报告 | `89/89` |
| 整体功能测试 | 新请求、同 Brief 恢复、Trace 关联、版本 Gate、Full Version 报告和 Skill 结构 smoke | 项目级 `90/90`；smoke `6/6` |

## 关键风险与处理

| 风险 | 已落地控制 | 剩余边界 |
|---|---|---|
| 中断导致重复扣费或重复外调 | checkpoint + idempotency key + operation receipt + CAS | 真实 Provider 自身的幂等语义需适配器确认 |
| Research/Worker 部分失败污染主状态 | staging、状态 fingerprint、copy-on-write、failure ledger | 当前外部执行后端仍由宿主提供 |
| 预算耗尽后继续工作 | 每阶段/外调前原子 charge，统一 `PARK` | Provider 在超时后的实际计费需靠 request/usage receipt 对账 |
| Evaluator 无限循环 | 轮次在调用前持久化，跨恢复总计最多两轮 | 真实 Evaluator 的输出质量尚未建立外部模型基线 |
| artifact 被替换或跨 run 复用 | current run/revision/quality gate + 文件存在性 + SHA-256 复核 | 业务特定 artifact 渲染尚未接默认 Runner |
| Prompt/model/provider 升级静默退化 | 稳定 fingerprint；变化强制当前非 mock live report；baseline 显式审批 | 当前 live runner 执行本地生产 API，不等价于外部模型评测 |
| 旧 Brief 或跳过测试污染发布 | FV-08 clean-room、八项 AC、`xfail/xpass=0`、证据 hash | 发布/安装流水线尚未建立 |
| 成本被伪装为零 | 仅接受 Provider usage；缺失时记录 `UNAVAILABLE` | 未接真实 Provider 时无法计算生产成本 |

## 运行边界

- 默认单命令路径实际编排 P0/P1/P2，可创建或恢复 Living Brief，并运行至合法停止。
- P4 Research、P5 Worker、P6 Evaluator/Artifact/Handoff 已有事务化、可观测、可验收的 Python API，但尚未挂入默认 `FullCycleRunner`。
- DeepSeek、Kimi、MiniMax 只有 provider-neutral 配置和合同；没有 HTTP Adapter、Dispatcher 或真实 Council 调用。
- `FULL_VERSION` 是用户定义八项 AC 的合同发布状态，不宣称外部 Provider 已生产可用。
- Governor 生成概念 handoff，不执行实施计划；Council 保持可选，不能用单模型角色扮演冒充真实多模型独立性。

## 可复核证据

| 证据 | 路径 |
|---|---|
| AC 清单 | `acceptance/manifest.json` |
| Full Version 报告 | `acceptance/report.json`、`acceptance/report.md` |
| 整体 Agent smoke | `acceptance/agent-functional-report.json` |
| live regression | `evals/live-report.json` |
| 显式批准 baseline | `evals/baseline-manifest.json` |
| 当前回归门禁 | `evals/gate-report.json` |
| 完整任务与验收定义 | `FULL_VERSION_ACCEPTANCE_PLAN.md` |
