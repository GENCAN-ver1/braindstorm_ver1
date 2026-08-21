# Brainstorm Governor 完整版验收计划

## 1. 目标与范围

完整版的定义不是“接入更多模型”，而是让现有 P0–P6 能力成为一个可恢复、可审计、可回归、可交付的完整运行系统。

本计划只以以下八项条件作为最终验收标准：

| ID | 完整版验收条件 |
|---|---|
| AC-01 | 一条命令从用户请求运行至合法停止或 `COMMIT` |
| AC-02 | 任意阶段中断后可从 Brief 恢复 |
| AC-03 | Research/Worker 部分失败不污染主状态 |
| AC-04 | Evaluator 永远不超过两轮 |
| AC-05 | 所有阶段预算耗尽都能保存 `PARK` |
| AC-06 | Trace 自动记录 P4/P5/P6 激活和真实成本 |
| AC-07 | Prompt、模型或 Provider 升级触发真实回归 |
| AC-08 | 只有通过质量门禁的现有 artifact 才能生成 handoff |

DeepSeek、Kimi、MiniMax Council 保持接口预留状态。Council Provider 的真实 HTTP 调用、并发执行和综合不属于本轮完整版主线，也不阻塞 AC-01～AC-08；将来启用时必须复用 P5 隔离、P6 Trace 和本计划的外部调用边界。

## 2. 当前基线与缺口（FV-08 完成后）

| 验收项 | 当前能力 | 完整版缺口 |
|---|---|---|
| AC-01 | 统一 `scripts/brainstorm.py run` 可从请求运行至合法停止 | 已完成，AC-01 为 `IMPLEMENTED` |
| AC-02 | 每阶段 durable checkpoint、revision/CAS、in-flight receipt 与幂等恢复已完成 | 已完成，AC-02 为 `IMPLEMENTED` |
| AC-03 | Research/Worker 深快照、staging、copy-on-write、failure ledger 与故障注入已完成 | 已完成；真实 Provider/Executor 和默认 FullCycle 接线不属于 AC-03 隔离断言 |
| AC-04 | Durable Evaluator Guard 已在 Provider 调用前原子预留轮次并跨恢复保持两轮硬上限 | 已完成；同一请求恢复复用 receipt，第三轮在 Provider 前拒绝，AC-04 为 `IMPLEMENTED` |
| AC-05 | 全阶段与外部调用已接入幂等 Budget Guard | 已完成；预算耗尽统一保存合法 `PARK`，AC-05 为 `IMPLEMENTED` |
| AC-06 | Runner Event Sink、P4/P5/P6 自动 activation、usage receipt 与版本化成本账本已完成 | 已完成；真实 HTTP Provider 的 usage 字段映射仍属于 Provider 集成工作 |
| AC-07 | 版本指纹、16 场景 live local regression、显式 baseline 与 CI Release Gate 已完成 | 已完成；Prompt/model/provider/adapter/schema/pricing 变化强制新 live report，AC-07 为 `IMPLEMENTED` |
| AC-08 | Artifact Writer、七字段 manifest、SHA-256 与 current run/revision quality gate 校验已完成 | 已完成；缺失、空文件、篡改、跨 run/revision 或非 `COMMIT` 均拒绝，AC-08 为 `IMPLEMENTED` |

## 3. 总体运行架构

```text
brainstorm run
      │
      ▼
Request + Config Loader
      │
      ▼
Lifecycle Runner
      ├─ Durable Checkpoint / Re-entry
      ├─ Global Budget Guard
      ├─ Transaction Boundary
      ├─ Trace + Usage Ledger
      │
      ├─ P0 Route
      ├─ P1 Core Loop
      ├─ P3 Challenge
      ├─ P4 Research       ── external-call boundary
      ├─ P5 Workers        ── external-call boundary
      ├─ P6 Evaluate       ── max 2 across the whole run
      │
      ▼
Artifact Writer → Quality Manifest → Restricted Handoff
      │
      ▼
Version Fingerprint + Regression Release Gate
```

Council 接口挂在 P5 external-call boundary 上；默认关闭，不进入 Runner 的必经路径。

## 4. 任务模块

### FV-00：验收清单与故障注入基座（已完成）

目标：先把八项条件变成可执行验收，而不是在实现结束后人工判断。

任务：

1. 建立 `acceptance/manifest.json`，固定 AC-01～AC-08 的测试 ID、输入 Fixture、预期状态和产物。
2. 建立阶段枚举矩阵：`INITIALIZE / ROUTE / CONTEXT / FRAME / DIVERGE / NORMALIZE / CHALLENGE / RESEARCH / CONVERGE / EVALUATE / COMMIT`。
3. 建立 fault injector，可在每个阶段的 `before_enter / after_checkpoint / before_external_call / after_external_call / before_commit` 注入异常或中断。
4. 建立主状态 fingerprint，至少覆盖：`frame / candidates / assumptions / unknowns / evidence / decisions / result`。
5. 定义验收报告结构：测试 ID、版本指纹、开始/结束时间、结果、失败原因、产物路径和 Trace 路径。

交付物：

```text
acceptance/manifest.json
acceptance/report.schema.json
runtime/fault_injection.py
runtime/state_fingerprint.py
tests/acceptance/
```

完成标准：八项 AC 均有至少一个自动化测试入口；阶段矩阵无遗漏。

完成证据：

- AC-01～AC-08 均已注册稳定测试 ID、Fixture、预期状态和预期产物；
- 11 个阶段和 5 个故障点与运行时枚举双向校验；
- fault injector 支持确定性的异常/中断、指定触发次数和审计事件；
- state fingerprint 覆盖七个主状态字段，忽略非主状态瞬态字段；
- FV-00 基座测试 `23/23`、现有 P0–P6 回归 `108/108`、Skill 校验通过；
- FV-00 完成时 AC 状态保持 `SCAFFOLDED`；后续模块只有通过真实行为验收才能逐项升级为 `IMPLEMENTED`，当前状态以 manifest 为准。

### FV-01：统一配置与单命令 Runner（已完成）

目标：满足 AC-01，并为其余模块提供唯一生命周期入口。

任务：

1. 实现版本化配置 Schema 和严格 Loader。
2. 实现 `FullCycleRunner`，只编排现有 P0–P6，不重写其业务合同。
3. 增加统一 CLI：

   ```text
   brainstorm run --request request.json --config brainstorm-governor.yaml --brief CONCEPT_BRIEF.md
   ```

4. 支持标准输入作为 request；输出机器可读的终止摘要。
5. 统一合法终止：`EXPLORE / RESEARCH_REQUIRED / ITERATE / COMMIT / PARK / NEEDS_INPUT`。
6. 非合同错误返回非零退出码；合法停止即使不是 `COMMIT` 也返回完整状态和恢复位置。
7. 默认关闭 Research、Workers 和 Council；只有配置与门禁同时允许时才激活。

交付物：

```text
config/brainstorm-governor.schema.json
config/brainstorm-governor.example.yaml
runtime/config_loader.py
runtime/full_cycle.py
scripts/brainstorm.py
```

AC-01 验收：

- 新请求一条命令可运行到六种合法停止之一；
- 运行中不要求人工调用 P0–P6 子脚本；
- 输出包含 `run_id / mode / exit_status / brief_path / next_action`；
- `COMMIT` 前不会进入实施 Agent。

完成证据：

- `config/brainstorm-governor.schema.json` 与严格 Loader 已实现，拒绝未知字段、错误类型、非法版本及越界并行/Evaluator 配置；
- 示例配置为零依赖可解析的合法 YAML，Research、Workers、Council、Evaluator 默认关闭；
- `FullCycleRunner` 已统一调用 P0 路由、P1 核心循环和 P2 Living Brief 持久化；
- CLI 同时支持请求文件和 stdin，合法停止返回机器可读摘要与退出码 `0`，合同错误返回退出码 `2`；
- 纯文本请求实际运行至合法 `NEEDS_INPUT` 并保存 Brief，不伪造模型内容或进入实施 Agent；
- AC-01 已标记 `IMPLEMENTED`，FV-00/FV-01 测试 `33/33`、P0–P6 回归 `108/108`。

### FV-02：Durable Checkpoint 与任意阶段恢复（已完成）

目标：满足 AC-02。

任务：

1. 扩展 Brief checkpoint envelope：

   ```text
   schema_version
   revision
   run_id
   last_completed_stage
   next_stage
   in_flight_operation
   idempotency_key
   state_hash
   trace_cursor
   evaluator_rounds_used
   usage_totals
   artifact_status
   ```

2. 每个阶段采用 `enter checkpoint → execute → validate → commit checkpoint`。
3. 外部调用前保存 in-flight 记录；恢复时按 idempotency key 判断重试、收集或安全停止。
4. 增加 Brief revision/CAS，拒绝并发旧版本覆盖。
5. 恢复顺序固定为：读取 Brief → 校验 Schema/hash → 恢复计数器和 Trace cursor → 决定重入点。
6. 禁止从聊天历史重建 `LOCKED` 决策。

交付物：

```text
runtime/checkpoint.py
runtime/reentry.py
runtime/idempotency.py
persistence/migrations/
```

AC-02 验收：

- 在阶段矩阵每个阶段注入中断，第二次运行均可从 Brief 恢复；
- 已完成阶段不重复产生副作用；
- `LOCKED` 决策、evaluator 次数、usage 和 Trace 连续；
- 恢复结果与不中断执行的状态 fingerprint 相同，允许 Trace 中多出恢复事件。

完成证据：

- checkpoint envelope 已内嵌于 P2 canonical Brief，覆盖计划字段，并增加 operation receipts 与 recovery count；
- `CheckpointStore` 使用同目录排他锁、revision 与文件 digest 执行 CAS，拒绝旧 revision 和任何旁路改写；
- 七字段主状态 hash 在每次 checkpoint 重算，篡改后恢复硬停止；
- `DurableStageRunner` 已实现 `before_enter → enter checkpoint → execute → validate → before_commit → commit checkpoint`；
- 外部调用在调用前保存 in-flight，在返回后保存 receipt，恢复按 `RETRY / COLLECT / PARK / REUSE_RECEIPT` 决策；
- Legacy P2 Brief 可显式迁移且不改变 `LOCKED` 决策；
- AC-02 已覆盖 11 个阶段 × 3 个通用中断边界，并覆盖外部调用前/后中断；恢复 fingerprint 与无中断基线一致；
- 实际 FullCycleRunner 的 P1 六阶段均完成中断恢复，并与原 P1 主状态 fingerprint 保持一致；
- Trace cursor、Evaluator 次数、usage totals、artifact status 跨恢复连续；FV-00～FV-02 测试 `44/44`。

### FV-03：全阶段 Budget Guard 与统一 `PARK`（已完成）

目标：满足 AC-05。该模块必须早于真实外部适配器接入。

任务：

1. 建立统一 `BudgetGuard`，所有阶段进入前和外部调用前必须消费预算。
2. 将 P0–P5 的预算异常转换为领域事件 `BudgetExhausted`，由 Runner 统一处理。
3. 预算耗尽时禁止继续调用模型、搜索或 Worker。
4. 生成合法终止状态：`stage=STOPPED`、`status=STOPPED`、`exit_status=PARK`。
5. 原子保存 Brief、Trace、累计 usage 和明确 `next_action`。
6. 恢复时不得重置 `used_steps`；只能由新 run 或显式增加预算继续。

交付物：

```text
runtime/budget_guard.py
runtime/lifecycle_errors.py
tests/acceptance/test_budget_park_matrix.py
```

AC-05 验收：

- 阶段矩阵每个阶段分别在预算临界点耗尽；
- 所有用例均生成可由 P0 validator 接受的 `PARK` Brief；
- 不向用户暴露未处理异常；
- `next_action` 精确指向被阻断的阶段；
- 预算耗尽后外部调用计数不再增加。

完成证据：

- `BudgetGuard` 在阶段工作和外部调用前执行一步 charge；charge 与 checkpoint revision 在同一次 CAS 原子写入；
- checkpoint envelope 保存 `budget_charges`，中断恢复复用稳定 charge key，不重复扣费；FV-02 旧 envelope 缺少该新增字段时可兼容读取并在下次保存补齐；
- P1 阶段预算由 Runner 统一管理；遗留 P0～P5 `StateValidationError` 预算错误可转换为 `BudgetExhausted` 领域事件；
- 预算耗尽统一保存 `stage=STOPPED / status=STOPPED / exit_status=PARK`，保留 Trace cursor、usage totals 和被阻断的 `next_stage`；
- 外部预算不足发生在 Provider 调用前，清除尚未执行的 in-flight 记录且调用计数保持不变；
- 重入不会重置 `used_steps`；只有配置上限显式高于 Brief 内上限时才解除 `PARK`；
- AC-05 覆盖 11 个阶段临界耗尽及外部调用临界耗尽；FV-00～FV-03 测试 `54/54`、P0～P6 回归 `108/108`、Skill 校验通过。

### FV-04：Research/Worker 事务隔离（已完成）

目标：满足 AC-03。

任务：

1. Research 和 Worker 使用主状态只读快照；禁止直接持有可变主状态引用。
2. 外部结果进入 staging area，依次经过 Schema、引用、冲突、去重和知识状态校验。
3. 只有整个 commit contract 通过后，才能以一次 copy-on-write 操作写入主状态。
4. 失败仅写入 operational failure ledger、Trace 和 checkpoint，不写入事实、推荐或 `LOCKED` 决策。
5. Worker 部分成功时保留经过验证的独立结果；是否提交由显式 policy 决定，默认 `validated-partial`。
6. 超时、限流、Provider 5xx、无效 JSON、错误引用和重复候选分别作为独立失败类型。

交付物：

```text
runtime/transaction.py
runtime/failure_ledger.py
adapters/research_runtime.py
adapters/worker_runtime.py
```

AC-03 验收：

- Research 在第 N 个问题失败时，失败结果不会成为 `KNOWN`；
- Worker 一部分失败时，主状态的 Frame、Decisions 和既有 Evidence fingerprint 不变；
- 校验失败不会产生半写入；
- 重试相同 idempotency key 不会产生重复 Evidence/Candidate；
- failure ledger 能定位失败 Provider、阶段和错误类别，checkpoint Trace cursor 随失败记录推进。

完成证据：

- `StateTransaction` 从主状态深快照开始，提交前校验原状态 fingerprint，成功时返回新的 copy-on-write 状态；
- P4 按 ResearchQuestion、P5 按 Worker batch 建立 staging validation unit，覆盖 Schema、citation、source conflict、知识状态和候选机制去重；
- 支持显式 `all-or-nothing` 与默认 `validated-partial`，任何失败均不得写入事实、推荐或 `LOCKED` 决策；
- checkpoint envelope 新增向后兼容的 append-only failure ledger，通过 CAS 幂等持久化，并分类记录 timeout、rate limit、Provider 5xx、invalid JSON、citation error 和 duplicate candidate；
- durable operation receipt 在恢复时直接复用，避免重复 Provider/Worker 调用及重复 Evidence/Candidate；
- AC-03 已标记 `IMPLEMENTED`；FV-00～FV-04 测试 `66/66`、P0～P6 回归 `108/108`、Skill 校验通过。

边界：FV-04 只完成 provider-neutral 事务适配器。真实 Research Provider、Citation Checker、Worker Executor 和默认 FullCycle 激活路径仍属于集成工作；独立 Trace Event Sink 已由 FV-05 完成。

### FV-05：自动 Trace 与真实成本账本（已完成）

目标：满足 AC-06。

任务：

1. Runner 内置 Event Sink，P4/P5/P6 不再依赖调用方手工记录 activation。
2. 每次外部调用写 `UsageReceipt`：

   ```text
   run_id
   stage
   provider
   model
   request_id
   prompt_tokens
   completion_tokens
   cached_tokens
   tool_calls
   latency_ms
   price_table_version
   calculated_cost
   currency
   usage_source
   ```

3. token 使用量优先使用 Provider 返回值；不得由文本长度伪造。
4. 使用版本化价格表计算成本；Provider 无法返回 usage 时标记 `UNAVAILABLE`，生产验收不得把它当作零成本。
5. Trace 自动记录 gate decision、P4/P5/P6 activation、重试、失败、checkpoint、恢复和 exit status。
6. Trace 与 Brief 分开保存，但通过 `run_id + revision + trace_cursor` 关联。

交付物：

```text
observability/events.py
observability/trace_sink.py
observability/usage_ledger.py
config/provider-pricing.json
```

AC-06 验收：

- 分别触发 P4、P5、P6，Trace 自动出现对应 activation；
- 每次真实模型/Provider 调用都有 usage receipt；
- Trace 汇总 token/tool/cost 与 receipt 求和一致；
- 重试成本不会被遗漏或覆盖；
- Council 关闭时不产生 Council activation。

完成证据：

- `FullCycleRunner` 默认创建 `<brief-path>.trace.json`，checkpoint 自动写阶段、checkpoint、恢复与 exit 事件；
- P4/P5 运行时及 `TracedEvaluator` 自动记录 gate 和 `P4_RESEARCH / P5_WORKER / P6_EVALUATOR` activation，Council 关闭时没有 Council activation；
- 每次实际外调生成严格 `UsageReceipt`；Provider 返回 token/tool 数据时按 `config/provider-pricing.json` 的版本化费率计算，缺失时记录 `usage_source=UNAVAILABLE` 和 `null`，不按文本长度估算；
- 失败尝试携带的 Provider usage 与后续重试分别以 request ID 入账，append-only ledger 不覆盖历史成本；
- Trace `summary`、checkpoint numeric usage totals 与 receipt 求和一致，并校验 `run_id + revision + trace_cursor` 链接；
- AC-06 已标记 `IMPLEMENTED`；FV-00～FV-05 测试 `74/74`、P0～P6 回归 `108/108`、Skill 校验通过。

边界：内置价格表只提供验收 fixture。真实 DeepSeek、Kimi、MiniMax 或其他 Provider 必须在 HTTP Adapter 中归一化官方 usage 字段并提供经审核的价格表版本；未接入时系统会诚实记录 `UNAVAILABLE`，不会报告伪造的零成本。

### FV-06：跨恢复 Evaluator 上限与 Artifact/Handoff 门禁（已完成）

目标：同时满足 AC-04 和 AC-08。

任务：

1. 将 `evaluator_rounds_used` 写入 checkpoint，由 Runner 而非单次函数调用维护。
2. 每次 Evaluator 调用前原子递增计数；中断恢复后继续使用原计数。
3. 第二轮后仍有实质修正时停止 `ITERATE`，禁止第三轮。
4. 实现 Artifact Writer 和 manifest：

   ```text
   artifact_path
   sha256
   run_id
   brief_revision
   quality_gate_id
   quality_status
   created_at
   ```

5. handoff 构建时重新检查文件存在、SHA-256、`COMMIT`、quality status 和 run/revision 归属。
6. artifact 生成后被修改、缺失或来自其他 run 时拒绝 handoff。

交付物：

```text
runtime/evaluator_guard.py
artifacts/writer.py
artifacts/manifest.py
runtime/handoff_gate.py
```

AC-04 验收：

- 单次运行最多两轮；
- 第一轮后中断再恢复，总计仍最多两轮；
- 重试同一 evaluator request 不重复计轮；
- 第三轮请求在调用 Provider 前被拒绝。

AC-08 验收：

- `COMMIT + approved quality + existing artifact + hash match` 才能生成 handoff；
- `EXPLORE / ITERATE / PARK / NEEDS_INPUT / RESEARCH_REQUIRED` 均拒绝；
- 空路径、缺失文件、篡改文件、其他 run artifact 均拒绝；
- handoff 仍严格限制为既定七个字段。

完成记录：

- checkpoint 保存 evaluator reservation/consumption key、`evaluator_rounds_used` 和当前 `quality_gate_id`，旧 FV-05 envelope 可兼容恢复；
- `TracedEvaluator` 在 Provider 前预留轮次；调用前中断重试同一轮，调用后中断优先复用 receipt，均不重复计数或外调；
- 第二轮仍有实质修正时沿用 P6 合同停止为 `ITERATE`，第三轮在 Provider 前抛出硬上限错误；
- Artifact Writer 以 `PENDING → 文件原子写入 → APPROVED/REJECTED → manifest` 顺序持久化，中断不会产生合法 handoff；
- AC-04、AC-08 已标记 `IMPLEMENTED`；FV-06 行为测试覆盖恢复、重试、六类 artifact 场景和全部非 `COMMIT` 停止态。

### FV-07：版本指纹与真实回归门禁（已完成）

目标：满足 AC-07。

任务：

1. 为以下对象生成稳定 fingerprint：

   ```text
   governor prompt/template
   evaluator prompt/template
   model provider + model ID + reasoning mode
   provider adapter version
   citation checker version
   output schema version
   pricing table version
   ```

2. 建立 baseline manifest，记录 fingerprint、真实回归结果、指标和成本。
3. CI 比较当前 fingerprint；任何 Prompt、模型或 Provider 变化都必须运行 live regression job。
4. Live regression 至少复用现有 12 个场景，并增加：Provider failure、resume、every-stage PARK、artifact tamper。
5. 质量阈值至少包含：constraint adherence、duplication、coverage、assumption discovery、mislabel rate、平均轮次和成本。
6. baseline 更新必须是显式审查动作；禁止失败后自动覆盖 baseline。

交付物：

```text
evals/version_fingerprint.py
evals/baseline-manifest.json
evals/live_runner.py
ci/regression-gate.*
```

AC-07 验收：

- 修改任意 Prompt 后，CI 自动要求真实回归；
- 修改 model ID 或 Provider/adapter 版本同样触发；
- 未运行、失败或超过阈值时阻止发布；
- 未变化时可复用有效 baseline，但仍运行离线合同回归；
- 报告包含失败 case、质量差异和成本差异。

完成记录：

- 指纹覆盖 governor/evaluator prompt、provider、model/reasoning、adapter、citation checker、schema 和 pricing；
- live local runner 直接执行生产 P0～P6 API，并补跑 Provider failure、resume、every-stage PARK、artifact tamper，共 16 场景；
- CI Gate 在指纹未变化时复用 hash-verified baseline，但仍实际运行 `108/108` 离线合同回归；任何维度变化均要求当前、非 mock、阈值通过的 live report；
- baseline 仅能通过带 approval ID、reviewer 和显式 `--approve` 的命令更新，失败报告不能成为 baseline；
- 当前未调用外部 Provider，成本诚实记录为 `UNAVAILABLE`；真实 Provider 接入后其 identity/adapter 变化会触发同一门禁。

### FV-08：端到端验收与发布门禁（已完成）

目标：一次性证明 AC-01～AC-08 同时成立。

任务：

1. 构建 clean-room 测试目录，不依赖既有 Brief。
2. 执行 happy path、合法非 COMMIT 停止和全阶段 fault matrix。
3. 执行 Research/Worker 部分失败、Evaluator 恢复、预算耗尽、artifact 篡改和版本升级场景。
4. 汇总单一 acceptance report，报告每项 AC 的证据链接和产物 hash。
5. 只有八项全部 PASS 才标记 Full Version；不接受以 xfail 跳过核心验收。

交付物：

```text
tests/acceptance/test_full_version.py
acceptance/report.json
acceptance/report.md
```

完成标准：AC-01～AC-08 全部 PASS，现有 P0–P6 回归保持全绿，Skill 校验通过。

完成记录：

- clean-room 不读取既有 Brief，单命令返回合法 `NEEDS_INPUT` 并生成可恢复 Brief/Trace；
- AC-01～AC-08 全部真实执行并通过，`xfail/xpass=0`；
- P0～P6 `108/108`、FV-07 Gate `ALLOW`、Skill 结构校验全部通过；
- `acceptance/report.json` 与 `acceptance/report.md` 保存逐项测试、证据路径、SHA-256、版本指纹和命令 transcript hash；
- 任一 gate 失败时只允许 `RELEASE_BLOCKED`，不能输出 `FULL_VERSION`。

## 5. 依赖关系与实施进程

```text
FV-00 Acceptance Harness
   ↓
FV-01 One-command Runner
   ↓
FV-02 Durable Checkpoint / Re-entry
   ↓
FV-03 Global Budget → PARK
   ↓
FV-04 Research / Worker Transactions
   ↓
FV-05 Automatic Trace / Real Cost
   ↓
FV-06 Evaluator Cap / Artifact / Handoff
   ↓
FV-07 Versioned Live Regression
   ↓
FV-08 End-to-end Acceptance
```

顺序理由：

- Runner 是所有跨阶段能力的唯一挂载点；
- Checkpoint 必须先于预算和外部调用，否则无法证明恢复安全；
- Budget Guard 必须先于真实 Provider，避免超预算后继续产生费用；
- 事务隔离稳定后才能接入 Trace 和真实 usage；
- Artifact 和回归必须基于稳定生命周期，不应反向驱动核心状态机重构。

## 6. 每个模块的固定交付流程

每个 FV 模块均按以下步骤执行：

1. **Contract freeze**：确认输入、输出、状态变化、失败类型、权限和持久化字段。
2. **Unit tests**：先用 fixture/mock 验证确定性合同。
3. **Fault tests**：覆盖超时、中断、重试、重复请求和无效输出。
4. **Integration tests**：连接相邻 P0–P6 模块；涉及外部调用时使用 sandbox。
5. **Acceptance mapping**：更新 AC 测试及证据，不允许只报告普通单测。
6. **Full regression**：运行现有全部测试，禁止为了新模块修改无关业务行为。
7. **Documentation**：更新配置 Schema、README、恢复规则、Trace 和兼容性说明。
8. **Exit review**：本模块完成标准全部满足后才能进入下一模块。

## 7. 最终验收矩阵

| AC | 必测用例 | 关键断言 | 主要模块 |
|---|---|---|---|
| AC-01 | 新请求 happy path；六种合法停止 | 单命令、无手工子步骤、输出可恢复摘要 | FV-01 |
| AC-02 | 每阶段 before/after 中断 | 恢复状态等价、无重复副作用、LOCKED 不变 | FV-02 |
| AC-03 | Research N/3 失败；Worker 1/3 失败；无效结果 | 无半写入、无事实污染、失败可审计 | FV-04 |
| AC-04 | 两轮未通过；第一轮后中断恢复 | 调用总数≤2，第三轮调用前拒绝 | FV-06 |
| AC-05 | 每阶段预算临界耗尽 | 合法 `PARK`、Brief 可恢复、无后续外调 | FV-03 |
| AC-06 | P4/P5/P6 各自触发；重试 | activation 自动、receipt 完整、真实成本一致 | FV-05 |
| AC-07 | 修改 Prompt/model/provider | 自动触发 live regression，失败阻断发布 | FV-07 |
| AC-08 | approved、未通过、缺失、篡改、跨 run artifact | 仅 approved existing hash-matched artifact 可 handoff | FV-06 |

## 8. Full Version Release Gate

发布候选必须满足：

```text
existing P0–P6 tests                  PASS
Council interface tests              PASS
AC-01 ... AC-08                       PASS
acceptance xfail/xpass                0
Skill validation                      PASS
live regression fingerprint           current
live regression quality thresholds    PASS
artifact and handoff integrity         PASS
```

任意一项失败，版本状态保持 `MVP` 或 `release-candidate`，不得标记为 `Full Version`。
