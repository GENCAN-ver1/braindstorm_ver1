# Brainstorm Web Host P7 开发交接

更新时间：2026-08-23（Asia/Shanghai）  
当前 P7 Gate：`DEVELOPING`  
主工作区：`D:\gate\personal_projects\projects\brainstorm`（branch `main`，HEAD `f46e6373a5bbbe963a0953b573da16243a5d2af4`）  
前端隔离 worktree：`D:\gate\personal_projects\projects\brainstorm\.worktrees\p7-web-mvp`（branch `codex/p7-web-mvp`，HEAD `12cd653c1738369d8603c90d1ac0571e001c5a0e`）

> 当前用户指令：停止继续实现，不再修改业务代码。本文件是交接记录，不代表验收通过。

## 1. 最终目标与验收标准

最终目标：在不修改 P0–P6 Governor 语义的前提下，交付一个本地可运行的 React + TypeScript + Vite Brainstorm Web Host Frontend MVP。终端用户应能通过结构化 UI 完成 Idea Intake、六 Frame Wizard、运行状态与 `NEEDS_INPUT` 恢复、External Capability/Council Gate、Human Gate，以及仅在 Governor `COMMIT` 时显示的正式 Final Handoff。真实后端、真实 Provider 调用、生产身份、部署、DNS、push、merge 和 PR 均不在本轮范围。

P6 authority：

- Handoff：`artifacts/brainstorm-web-host-v2.p6-handoff.json`
- Pinned SHA-256：`f559307a6dde234be436cfaa2aa59097f1626e28b7fd6fd2a1971724ef858421`
- Approved artifact：`artifacts/brainstorm-web-host-v2.approved.json`
- Locked decision：候选 `c1`（结构化 guided Web Host）
- Open questions：无

不可弱化的验收标准：

1. 标准跳过路径、`NEEDS_INPUT` 恢复、Council 双 Provider 授权、Provider 失败和刷新恢复均可在浏览器完成；typecheck、lint、行为测试、production build、E2E、无障碍、React 与安全审查全部通过。
2. 终端用户无需查看或编辑 Governor JSON 即可完成 Idea Intake 和六 Frame Wizard。
3. 四种 Idea stage 选择分别且仅映射到 `Shape`、`Spark`、`Stress`、`Decide`。
4. 六 Frame 映射到约定 canonical 字段，并保留 `UNKNOWN`、`ASSUMPTION`、`KNOWN`、`CONFLICT`；AI 建议不得自动成为 `KNOWN`。
5. 运行页表达完整阶段、Governor 合法状态，并允许 `NEEDS_INPUT` 在同一 session lineage 中补充信息后恢复。
6. External Capability Gate 支持 Council Enable/Skip、至少两个独立 Provider 的校验和调用前显式授权。
7. API key 仅存在于 capability screen 的临时组件状态，不进入持久化、URL、日志、telemetry、manifest、Living Brief、Trace 或真实测试 fixture。
8. Human Gate 支持 Confirm、Request iteration 和 Provide missing input，且只有 Governor `COMMIT` 才显示正式 Final Handoff。
9. 标准跳过、`NEEDS_INPUT`、Council、Provider failure 和刷新恢复场景均通过行为测试与真实浏览器 E2E。
10. 在 390、768、1280、1440 代表性视口验证键盘导航、焦点、标签、错误关联、对比度和 reduced motion。
11. 前端 typecheck、lint、单元与集成测试、production build、React review、UI review、安全审查、P7 validator 和 P0–P6 regression 全部通过。

## 2. 已完成内容

### P0–P6 authority

- 创建独立 Brainstorm Web Host 请求、Living Brief、Trace、质量 artifact、artifact manifest 与严格 7 字段 P6 handoff。
- 用户已明确授权建立新的独立 Brainstorm Web Host P0–P6 handoff，并锁定 `c1`。
- v2 使用带 7 类显式检查的 deterministic local `ContractEvaluator`；v1 产物仅保留为审计轨迹，不能作为当前 authority。
- handoff SHA 已计算并固定到 `p7-manifest.json`。

### P7 合同与计划

- `p7-manifest.json` 已从旧 diet-app bootstrap 切换为 `brainstorm-web-host`，记录最小架构、T1–T5 DAG、前端/安全边界和 A1–A11。
- P7 validator 已对当前 manifest 返回 `valid: true`、gate `DEVELOPING`、无 warning/error。
- 已在隔离 worktree 写入冻结的 frontend contract 和逐任务 TDD 计划。

### T1 前端基础

- commit `2f2030d1ff23d49073b0c2cc20ac0271cf5f771c`：React/TS/Vite/Vitest/ESLint/npm 工具链、typed contracts、精确映射、versioned allowlisted session persistence 和首批测试。
- commit `12cd653c1738369d8603c90d1ac0571e001c5a0e`：强化 `MissingInputSubmission`/`CapabilityRequest` 联合类型、恢复输入边界、storage 写失败 Result、默认 non-watch test 和 Node engines。
- T1 规格审查：PASS。
- T1 质量复审：两个 HIGH 已关闭；最后剩余的 1 MEDIUM（`getItem` 抛异常）和 1 LOW（Node engines 范围）已修复到工作树，但尚未提交、尚未复跑 Vitest。

## 3. 修改/新增文件清单

### 主工作区：本任务新增或修改

- `.agents/skills/p7-web-host-development/SKILL.md`：P7 Governor 入口、合法 gate 和开发循环。
- `.agents/skills/p7-web-host-development/references/architecture.md`：最小架构规则。
- `.agents/skills/p7-web-host-development/references/contracts.md`：P6 handoff 与 P7 manifest schema。
- `.agents/skills/p7-web-host-development/references/task-graph.md`：依赖有效的任务 DAG 规则。
- `.agents/skills/p7-web-host-development/references/frontend-contract.md`：前端状态、响应式、可访问性要求。
- `.agents/skills/p7-web-host-development/references/security-contract.md`：信任边界、secret 和基线控制。
- `.agents/skills/p7-web-host-development/references/acceptance.md`：证据与 `COMMIT` 门禁。
- `.agents/skills/p7-web-host-development/references/skill-routing.md`：开发能力路由边界。
- `.agents/skills/p7-web-host-development/scripts/validate_p7.py`：deterministic P7 manifest validator。
- `.gitignore`：仅加入 `.worktrees/`，使隔离 worktree 不进入主工作区状态。
- `brainstorm-web-host.brainstorm.json`：独立 Brainstorm Web Host P1 请求与四个候选。
- `config/brainstorm-web-host.yaml`：Stress 模式、64 steps、evaluator enabled；research/workers/council disabled。
- `scripts/run_brainstorm_web_host_quality.py`：将用户授权应用到 v2 Brief，执行 bounded P6 evaluator，写 approved artifact/handoff。
- `BRAINSTORM_WEB_HOST_BRIEF.md`、`.trace.json`：v1 审计轨迹；不作为当前 authority。
- `BRAINSTORM_WEB_HOST_BRIEF_V2.md`、`.trace.json`：当前 v2 Living Brief 与 Trace。
- `artifacts/brainstorm-web-host.approved.json`、`.manifest.json`、`brainstorm-web-host.p6-handoff.json`：v1 审计产物；不要用于继续实现。
- `artifacts/brainstorm-web-host-v2.approved.json`、`.manifest.json`、`brainstorm-web-host-v2.p6-handoff.json`：当前 approved authority 链。
- `p7-manifest.json`：当前 P7 canonical development state，gate 为 `DEVELOPING`。
- `HANDOFF.md`：本交接文件；这是本次“停止实现”请求唯一新增文件。

### 隔离 worktree：未跟踪文档

- `docs/p7/brainstorm-web-frontend-contract.md`：冻结 types、四 mode 映射、六 Frame 映射、API boundary、mock/secret/COMMIT 规则；authority 已指向 v2 handoff + SHA。
- `docs/superpowers/plans/2026-08-23-brainstorm-web-mvp.md`：T1–T5 的 RED→GREEN 文件级实施计划。

### 隔离 worktree：T1 已提交文件

- `web/package.json`：React 19/Vite/Vitest/ESLint scripts 与依赖。
- `web/package-lock.json`：npm lockfile。
- `web/.gitignore`：忽略 `node_modules`、`dist` 和 TS build info。
- `web/index.html`：Vite HTML shell；尚无 `src/main.tsx`，因此还不能 build/run。
- `web/vite.config.ts`：React + Vitest/jsdom 配置。
- `web/tsconfig.json`、`web/tsconfig.app.json`、`web/tsconfig.node.json`：TypeScript project references/config。
- `web/eslint.config.js`：TypeScript/React Hooks/React Refresh lint 配置。
- `web/src/test/setup.ts`：Testing Library DOM matchers setup。
- `web/src/types/contracts.ts`：Governor/domain/API/error/session/secret types；Capability 与 missing input 使用受约束联合类型。
- `web/src/types/contracts.typecheck.ts`：合法/非法类型组合的编译期负例。
- `web/src/types/mappings.ts`：四 stage→mode、六 Frame→canonical field 映射、AI `ASSUMPTION` 与继续条件验证。
- `web/src/types/mappings.test.ts`：映射、UNKNOWN/blank blocking、AI classification 测试。
- `web/src/state/sessionPersistence.ts`：v1 allowlisted `sessionStorage` projection、恢复校验与 storage failure Result。
- `web/src/state/sessionPersistence.test.ts`：round-trip、secret exclusion、畸形/越界/Storage failure 测试。

### 隔离 worktree：当前未提交的 4 个 T1 修复文件

- `web/package.json`：Node engines 从 `>=20.19.0` 收窄为 Vite 7 对齐的 `^20.19.0 || >=22.12.0`。
- `web/package-lock.json`：同步 engines 元数据。
- `web/src/state/sessionPersistence.ts`：将 `storage.getItem()` 放进 `try/catch`，Storage 不可访问时恢复为 `null`。
- `web/src/state/sessionPersistence.test.ts`：新增 `getItem` 抛 `SecurityError` 的测试。

### 与本任务混在同一仓库、但不要归入本任务的现有脏文件

- 主工作区 tracked：`README.md`、`evals/baseline-manifest.json`、`evals/live-report.json`、已删除的 `quant_cognitive_restructure.json`。
- 主工作区 diet-app/council 相关未跟踪文件：`DIET_APP_*`、`diet-control-app.*`、`config/diet-*`、`adapters/council_http.py`、`adapters/openai_evaluator.py`、`scripts/run_diet_app_*`、相关 tests/artifacts/evidence/staging 等。
- 两个工作区的 `__pycache__` 变化是执行 Python 测试产生的噪声，不要提交为 P7 Web 改动。

## 4. 当前实现进度与未完成范围

- T1：功能实现完成，两个 commit 已存在；最后 4 文件的审查修复未提交且最终 Vitest 未复跑。`p7-manifest.json` 仍正确保守地标为 `in_progress`。
- T2：未开始。缺少 `src/main.tsx`、App shell、router、SessionContext、Idea Intake、六 Frame Wizard 和行为/集成测试。
- T3：未开始。缺少 typed mock API/state machine、Run/`NEEDS_INPUT`、Capability/Council、Human Gate、COMMIT-only Handoff 和相关测试。
- T4：未开始。缺少视觉 tokens/global styles、响应式实现、可访问性专项测试。
- T5：未开始。没有 production build、真实浏览器 E2E、React/UI/security review、durable acceptance evidence 或最终 P7 gate 更新。
- 主工作区尚未包含 `web/` 与 `docs/`；它们只在隔离 worktree/branch 中。
- 当前不得宣称 `FRONTEND_READY_FOR_BACKEND_INTEGRATION`、`P7_WEB_MVP_READY` 或 P7 `COMMIT`。

## 5. 已执行测试/构建及结果

### 主工作区 P0–P6 基线

- `python -m unittest discover -s tests -q`：108 tests，OK。
- `python -m unittest discover -s .agents/skills/brainstorm-governor/tests -q`：108 tests，OK。
- `python ci\regression_gate.py check`：`ALLOW`。
- `python acceptance\full_version.py validate-report`：PASS。
- `python .agents\skills\p7-web-host-development\scripts\validate_p7.py --root . --manifest p7-manifest.json`：`valid: true`，gate `DEVELOPING`，0 errors，0 warnings。

### P6 Web Host authority

- `python scripts\brainstorm.py run --request brainstorm-web-host.brainstorm.json --config config\brainstorm-web-host.yaml --brief BRAINSTORM_WEB_HOST_BRIEF_V2.md`：完成 P0/P1 流程并在 Human Gate 合法停为 `NEEDS_INPUT`，推荐 `c1`。
- `python scripts\run_brainstorm_web_host_quality.py`：`COMMIT`，quality gate `quality:brainstorm-web-host-v2:round-1`；生成 v2 approved artifact/handoff。
- v2 approved artifact SHA：`259ad3f8782e6545095f2755a3cda4058b9640934046df8c09a5c019abbc7690`，与 artifact manifest 一致。
- v2 handoff SHA：`f559307a6dde234be436cfaa2aa59097f1626e28b7fd6fd2a1971724ef858421`，与 P7 pin 一致。

### 隔离 worktree T1

- 初始 RED：2 suites 因缺少 `./mappings`、`./sessionPersistence` 失败，符合 TDD 预期。
- 首次 GREEN：2 files / 8 tests passed；typecheck、lint 通过；npm audit 0 vulnerabilities。
- HIGH 修复 RED：14 个新增 runtime 边界测试失败，7 个 unused `@ts-expect-error` 证明非法类型仍可构造。
- HIGH 修复 GREEN：2 files / 21 tests passed；typecheck、lint 通过。
- 最后 4 文件修复后：`npm run typecheck` 通过，`npm run lint` 通过。
- 最后新增的 `getItem SecurityError` 测试尚未执行：Windows sandbox 内 Vite/esbuild 报 `spawn EPERM`；申请 sandbox 外执行时因 Codex 使用额度上限被系统拒绝。不要记作测试通过。
- `npm run build`：未执行。T1 按计划没有创建属于 T2 的 `src/main.tsx`，当前 build 不应预期成功。
- 浏览器 E2E：未执行。
- 隔离 worktree 根目录 Python 测试曾为 90 tests / 3 failures；这是该 worktree 基于旧 HEAD、未包含主工作区未提交 release artifact/baseline 修复造成的既有差异，不是 T1 Web 回归，但最终验收必须在正确集成状态重新跑。

## 6. 已知 bug、失败测试与风险

1. **未验证/未提交修复**：最后 4 个 T1 文件仍在 worktree working tree；typecheck/lint 通过，但新增 Vitest 未复跑。
2. **环境阻塞**：Vite/Vitest/esbuild 在当前 Windows sandbox 内可能 `spawn EPERM`；之前沙箱外运行可通过，但最后一次 sandbox 外申请因 Codex 使用额度上限被拒绝。不可绕过该限制；额度/授权恢复后再跑。
3. **manifest 路径不一致**：`p7-manifest.json` T1 output 写成 `web/src/domain/mappings.ts`，实际冻结计划和实现是 `web/src/types/mappings.ts`。接手后应在有证据更新 T1 状态时一并修正，不要移动实现去迁就错误路径。
4. **manifest/详细计划命名不一致**：manifest 的 T2/T3 示例输出使用 `IdeaIntake.tsx`、`features/frames`、`ExternalCapabilityGate` 等路径，而详细计划使用 `IdeaIntakePage.tsx`、`features/frame`、`features/external-capability`。以冻结 contract + 详细计划为准，并在开始对应任务前统一 manifest 路径；不要同时创建两套目录。
5. **Council distinct provider**：T1 静态类型只保证 Council 至少两个 Provider，无法保证名称互异；T3 必须做 runtime distinct-name 校验。
6. **route allowlist 联动**：T2 新增真实路由时必须同步 `sessionPersistence.ts` 的 route allowlist 和测试，否则刷新恢复会返回 `null`。
7. **mock 边界风险**：development mock 只能在 dev/test 选择，页面必须持续标注 “Development simulation”，production 不得误称真实 Governor/Provider。
8. **secret 风险**：API key 只能存在 capability screen 临时组件 state；不得传入 SessionContext、persistence、URL、日志、telemetry、fixture、manifest、Brief 或 Trace。
9. **状态语义风险**：非 `COMMIT` 不得显示 “Final / Approved / Ready for implementation”；`NEEDS_INPUT` resume 必须保留同一 session lineage 和 revision conflict 行为。
10. **依赖提示**：安装时出现 ESLint 9.39.5 支持期提示和 esbuild install-script review warning；当前 audit 0 vulnerabilities，但 T5 仍需正式 dependency review。
11. **脏工作区风险**：主工作区和隔离 worktree 都有大量 Python cache/用户改动。禁止 `git reset --hard`、`git checkout -- .`、批量 clean 或将所有状态一次性 stage。

## 7. 已确定且不应重复推翻的架构/技术决策

- 前端栈固定为 React 19 + TypeScript + Vite + npm/package-lock；测试使用 Vitest + React Testing Library，routing 使用 React Router。
- 后端 Governor 与 Living Brief 是 canonical truth；浏览器只拥有 typed UI projection。
- React component 不直接调用 `fetch`；所有异步行为通过 typed `BrainstormApi` boundary。
- 当前仅实现显式标注的 development-only mock adapter；不实现或暗示真实后端/Provider。
- 状态管理使用 React context + local state，不增加大型状态库。
- 刷新恢复只使用 versioned、allowlisted、non-secret `sessionStorage` projection；storage 不可用时安全降级。
- Provider key 使用 `EphemeralProviderSecret` 概念，仅驻留 capability screen 组件临时 state；凭据存在不等于授权。
- Idea stage 映射固定且只有四项：idea→`Shape`、explore→`Spark`、solution→`Stress`、decision→`Decide`。
- 六 Frame/canonical 字段固定：Who & Job→`target_user/core_task`；Desired Change→`desired_change`；Constraints→`hard_constraints`；Success→`success_metrics`；Failure Boundary→`abandonment_criteria`；Scope & Validation→`non_goals/validation_horizon`。
- AI suggestion 初始必须为 `ASSUMPTION`；只有用户显式确认才能成为 `KNOWN`。
- Council Enable 需要至少两个名称互异且 URL/model/key 合法的 Provider，并在调用前显式授权；Skip 是一等结果。
- Formal Handoff 仅在 `governorStatus === 'COMMIT'` 渲染。
- 本轮不部署、不配置 DNS、不保存真实凭据、不 push、不 merge、不创建 PR。

## 8. 建议接手顺序

1. 先阅读本文件、`p7-manifest.json`、v2 P6 handoff、`docs/p7/brainstorm-web-frontend-contract.md` 和详细实现计划；确认在隔离 worktree `codex/p7-web-mvp` 工作。
2. 只检查当前 4 个未提交 T1 diff；额度/权限恢复后先跑 focused Vitest、full Vitest、typecheck、lint。全部通过后仅 stage 这 4 个文件并提交；不要 stage pycache/docs。
3. 对最后修复做一次只读质量复审。若无 CRITICAL/HIGH，把 T1 视为完成；将冻结 docs 作为单独受审提交保留。
4. 修正 `p7-manifest.json` 的 T1 mappings path 和未来 T2/T3 路径命名；仅在证据存在后将 T1 改为 `done`、T2 改为 `in_progress`，保持最多一个 `in_progress`。
5. 严格按详细计划 T2 做 RED→GREEN：App shell/router/SessionContext/Idea Intake/六 Frame Wizard/刷新恢复。
6. T2 规格/质量审查通过后再做 T3：typed API + development mock state machine + Run/NEEDS_INPUT + Capability/Council + Human Gate + COMMIT-only Handoff。
7. T3 通过后做 T4：视觉系统、390/768/1280/1440 响应式、键盘/焦点/标签/错误关联/对比度/reduced motion。
8. 最后做 T5：production build、真实浏览器场景、React performance review、最新 Web Interface Guidelines review、安全审查；修复全部 CRITICAL/HIGH 和 P7 violation。
9. 将 `web/`、冻结 docs 和 acceptance evidence 安全地带回主工作区，避免覆盖现有脏文件；在正确集成状态重跑 P7 validator、P0–P6 tests、regression gate、FV report validation。
10. 只有 A1–A11 均有 durable evidence 且 P7 validator `valid: true`，才能把 gate 设为 `COMMIT`；否则保持 `DEVELOPING`/`BLOCKED`。

## 9. 不要随意修改的文件/边界

- `artifacts/brainstorm-web-host-v2.p6-handoff.json` 及其 SHA：P7 authority，不得编辑或替换。
- `artifacts/brainstorm-web-host-v2.approved.json` 与 `.manifest.json`：approved evidence chain，不得覆盖。
- `BRAINSTORM_WEB_HOST_BRIEF_V2.md` 与 `.trace.json`：P0–P6 audit/state，不得手改以伪造状态。
- `p7-manifest.json` 中 A1–A11 原文、三个 non-goals、source handoff path/SHA：不可弱化或删除；只能基于真实证据更新 task/status/evidence 和纠正已知路径错误。
- `.agents/skills/brainstorm-governor/**`、`runtime/**`、`persistence/**`、`observability/**`、`acceptance/**`、`ci/**`：本轮非目标，不要为前端便利修改 Governor runtime。
- `README.md`、`evals/baseline-manifest.json`、`evals/live-report.json`、`quant_cognitive_restructure.json` 及 diet-app/council 文件：已有用户/其他任务改动，不要回退、删除、覆盖或纳入 Web commit。
- `web/src/types/contracts.ts`、`web/src/types/mappings.ts`、`web/src/state/sessionPersistence.ts`：T1 已审查的边界；后续应增量兼容，非必要不要推翻类型/安全设计。
- 不要提交真实 API key、token、credential 或包含它们的 fixture/screenshot/log。

## 10. Git 状态快照

以下快照在创建本文件后由 `git status --short`、`git diff --stat` 获取。`git diff --stat` 不显示未跟踪文件，因此必须结合 status 阅读。

### 主工作区

`git status --short` 关键项：

```text
 M README.md
 M evals/baseline-manifest.json
 M evals/live-report.json
 D quant_cognitive_restructure.json
?? .agents/skills/p7-web-host-development/
?? .gitignore
?? BRAINSTORM_WEB_HOST_BRIEF.md
?? BRAINSTORM_WEB_HOST_BRIEF.md.trace.json
?? BRAINSTORM_WEB_HOST_BRIEF_V2.md
?? BRAINSTORM_WEB_HOST_BRIEF_V2.md.trace.json
?? HANDOFF.md
?? artifacts/brainstorm-web-host-v2.approved.json
?? artifacts/brainstorm-web-host-v2.approved.json.manifest.json
?? artifacts/brainstorm-web-host-v2.p6-handoff.json
?? artifacts/brainstorm-web-host.approved.json
?? artifacts/brainstorm-web-host.approved.json.manifest.json
?? artifacts/brainstorm-web-host.p6-handoff.json
?? brainstorm-web-host.brainstorm.json
?? config/brainstorm-web-host.yaml
?? p7-manifest.json
?? scripts/run_brainstorm_web_host_quality.py
```

此外 status 还包含本文件第 3/9 节所述 diet-app/council、evidence/staging、中文结论文件和 Python `__pycache__` 未跟踪项；均不得误纳入本 Web Host 提交。

`git diff --stat`（只含 tracked diff，不含上述未跟踪 P7 文件）：

```text
 README.md                        | 573 +++++++++++++++++++++++++--------------
 evals/baseline-manifest.json     |   8 +-
 evals/live-report.json           |  20 +-
 quant_cognitive_restructure.json | 171 ------------
 4 files changed, 387 insertions(+), 385 deletions(-)
```

### 隔离 worktree

`git status --short` 关键项：

```text
 M web/package-lock.json
 M web/package.json
 M web/src/state/sessionPersistence.test.ts
 M web/src/state/sessionPersistence.ts
?? docs/
```

此外有 68 个 tracked Python `__pycache__` binary 变化，以及 3 个未跟踪 cache 路径；它们是测试执行噪声，不要 stage。`git diff --cached --stat` 为空，当前没有 staged change。

`git diff --stat`：

```text
 68 Python __pycache__ binary files                  | binary-only changes
 web/package-lock.json                               |   2 +-
 web/package.json                                    |   2 +-
 web/src/state/sessionPersistence.test.ts            |  10 ++++++++++
 web/src/state/sessionPersistence.ts                 |   6 +++---
 72 files changed, 15 insertions(+), 5 deletions(-)
```

换行提示：Git 报告上述 4 个 `web/` working-copy 文件下次处理时可能由 LF 转为 CRLF；提交前应检查差异，避免产生无关整文件换行改动。
