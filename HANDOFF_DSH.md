# Brainstorm Web Host P7 开发交接（DSH）

更新时间：2026-08-24（Asia/Shanghai）  
当前 P7 Gate：`DEVELOPING`（非 `COMMIT`）  
主工作区：`D:\gate\personal_projects\projects\brainstorm`（branch `main`，HEAD `45547bceb98a195303e582e5f95bb4251867d780`）  
历史隔离 worktree：`.worktrees/p7-web-mvp`（branch `codex/p7-web-mvp`，HEAD `6ff99f01d3a6eddc39f9d10bb2b192b2e4d4f7ab`，已被主工作区取代，仅保留为审计轨迹）

> 本文件是 DSH（DeepSeek Harness）接手 Codex 交接后，完成 T1–T5（除真实浏览器 E2E/视觉审查外）的二次交接记录，不代表验收通过（`COMMIT`）。

## 1. 最终目标与验收标准

最终目标：在不修改 P0–P6 Governor 语义的前提下，交付一个本地可运行的 React + TypeScript + Vite Brainstorm Web Host Frontend MVP。终端用户通过结构化 UI 完成 Idea Intake、六 Frame Wizard、运行状态与 `NEEDS_INPUT` 恢复、External Capability/Council Gate、Human Gate，以及仅在 Governor `COMMIT` 时显示的正式 Final Handoff。真实后端、真实 Provider 调用、生产身份、部署、DNS、push、merge 和 PR 均不在本轮范围。

P6 authority：

- Handoff：`artifacts/brainstorm-web-host-v2.p6-handoff.json`
- Pinned SHA-256：`f559307a6dde234be436cfaa2aa59097f1626e28b7fd6fd2a1971724ef858421`
- Approved artifact：`artifacts/brainstorm-web-host-v2.approved.json`
- Locked decision：候选 `c1`（结构化 guided Web Host）
- Open questions：无

11 条验收标准（A1–A11，与 `p7-manifest.json` / v2 handoff 原文一致）。当前状态：

| ID | 状态 | 说明 |
|---|---|---|
| A1 | unverified | 浏览器完成标准跳过/`NEEDS_INPUT`/Council/Provider 失败/刷新恢复 + 全套审查（需真实浏览器） |
| A2 | pass | 无需查看/编辑 Governor JSON 即可完成 Idea Intake 和六 Frame Wizard |
| A3 | pass | 四 Idea stage 分别且仅映射 Shape/Spark/Stress/Decide |
| A4 | pass | 六 Frame 映射 canonical 字段，保留 UNKNOWN/ASSUMPTION/KNOWN/CONFLICT；AI 建议不自动成 KNOWN |
| A5 | pass | 运行页表达完整阶段/合法状态，`NEEDS_INPUT` 同 lineage 恢复 |
| A6 | pass | Council Enable/Skip、≥2 独立 Provider 校验、调用前显式授权 |
| A7 | pass | API key 仅存 capability screen 组件 state，不进持久化/URL/日志/telemetry/manifest/Brief/Trace/fixture |
| A8 | pass | Human Gate 支持 Confirm/Request iteration/Provide missing input；仅 COMMIT 显示 Final Handoff |
| A9 | unverified | 场景需「行为测试 + 真实浏览器 E2E」（行为测试已过，E2E 未跑） |
| A10 | unverified | 390/768/1280/1440 视口、键盘/焦点/对比度/reduced motion（需浏览器） |
| A11 | unverified | typecheck/lint/单测/build/validator/regression 已过；React review/UI review 需浏览器 |

## 2. 已完成内容（DSH 本轮）

### 环境与 Git 治理

- 解除 Windows 沙箱 `spawn EPERM`（esbuild/vitest/npm 脚本需 `danger-full-access`；tsc/eslint 纯 Node 不受限）。
- 确立主工作区 `main` 为**唯一事实来源**：`web/` 与 `docs/` 已合并进主工作区；worktree `codex/p7-web-mvp` 冻结为审计轨迹，不再在其中开发。

### T1 收尾

- 4 个未提交审查修复（engines 收窄、`getItem` 移入 try/catch、新增 SecurityError 测试）已提交到 worktree `bafe715`，并随 `web/` 合并进主工作区 `902e71c`。
- T1 规格/质量复审通过（typecheck/lint/vitest 22/22）。

### T2 前端基础（`482bc02`）

- `main.tsx`、`app/{App,router,AppShell}.tsx`、`state/SessionContext.tsx`、`features/intake/IdeaIntakePage.tsx`、`features/frame/{FrameWizardPage,frameDefinitions}.ts`、`components/{StatusBadge,FormError}.tsx` + 测试。持久 “Development simulation” 标签。

### T3 门禁流（`c7eb070`）

- `api/{BrainstormApi,errors,client,developmentMock}.ts`：typed `BrainstormApi` + 无状态 development mock 状态机（sessionStorage 持久化，永不持久化 provider key）。
- `features/run/{RunPage,NeedsInputPanel,stages}.ts`、`features/external-capability/{ExternalCapabilityGate,CouncilForm,AuthorizationReview}.tsx`、`features/human-gate/HumanGatePage.tsx`、`features/handoff/HandoffPage.tsx` + 测试。

### T4 视觉/无障碍（`c954f96`）

- `styles/{tokens,global,components}.css`：calm 高密度视觉系统、`prefers-reduced-motion`、`:focus-visible`、响应式（≤767px）、`role="alert"` + `aria-describedby` 错误关联、`accessibility.test.tsx`。

### T5 可执行部分（`45547bc`）

- production build 通过；P0–P6 回归无损；`artifacts/acceptance/brainstorm-web-host-{test,browser,security}-report.md` durable evidence；代码级安全审查；A2–A8 标记 `pass` 并挂证据。

## 3. 修改/新增文件清单（本轮 DSH，相对初始 handoff 快照 `3949387`）

主工作区 `main` 新增/修改：

- `p7-manifest.json`：T1→done、T2→done、T3→done、T4→done、T5→in_progress；修正 T1 mappings 路径、T2/T3 命名对齐冻结计划；A2–A8 状态/证据；gate summary 更新。
- `web/`（整个前端，42 个 `web/src/` 文件 + 配置/锁文件）：T1 契约与持久化、T2 壳/向导、T3 API+门禁、T4 样式。
- `docs/p7/brainstorm-web-frontend-contract.md`、`docs/superpowers/plans/2026-08-23-brainstorm-web-mvp.md`（从 worktree 带入）。
- `artifacts/acceptance/brainstorm-web-host-{test,browser,security}-report.md`：T5 证据。
- `HANDOFF_DSH.md`：本交接文件。

未提交的噪声（不要纳入提交）：2 个 Python `__pycache__` 未跟踪项（跑 P0–P6 测试产生）。

## 4. 当前实现进度与未完成范围

- T1：完成。T2：完成。T3：完成。T4：完成。
- T5：**部分完成**——typecheck/lint/单测/build/P7 validator/P0–P6 回归/evidence/安全审查均已做；**唯一未完成项是真实浏览器 E2E + 视口/键盘/焦点/对比度/reduced-motion 审计 + React/UI 审查**（需 Playwright/`control-in-app-browser`，本环境不提供）。
- 当前不得宣称 `P7_WEB_MVP_READY` 或 P7 `COMMIT`。

## 5. 已执行测试/构建及结果

### 前端（`web/`）

| 检查 | 命令 | 结果 |
|---|---|---|
| Typecheck | `npm run typecheck` | exit 0 |
| Lint | `npm run lint` | exit 0（1 warning：SessionContext `useSession` react-refresh，惯用） |
| 单元/集成 | `npx vitest --run` | 11 files / **51 tests passed** |
| Build | `npm run build` | exit 0（64 modules；CSS 3.96kB、JS 258.83kB） |
| P7 validator | `validate_p7.py --root . --manifest p7-manifest.json` | `valid:true`，0 errors/warnings |

### P0–P6 回归（主工作区）

| 检查 | 命令 | 结果 |
|---|---|---|
| 仓库测试 | `python -m unittest discover -s tests -q` | 108 OK |
| Skill 测试 | `python -m unittest discover -s .agents/skills/brainstorm-governor/tests -q` | 108 OK |
| 回归门 | `python ci\regression_gate.py check` | `ALLOW` |
| Full Version | `python acceptance\full_version.py validate-report` | `PASS` |

### 运行方式

```powershell
cd web
npm run dev                    # 开发（http://localhost:5173）
# 或
npm run build ; npx vite preview  # 生产构建预览（http://localhost:4173）
```

## 6. 已知问题、失败测试与风险

1. **浏览器 E2E 未跑（最大风险）**：A1/A9/A10/A11 的浏览器部分未验证；jsdom 行为测试不能替代真实浏览器。
2. **mock 未按 `import.meta.env.DEV` 门控**：`developmentMock` 始终是 adapter。因 app 恒显 “Development simulation” 且非目标是「不宣称真实后端」，MVP 可接受；生产需真 `BrainstormApi`（非目标）。
3. **react-refresh 1 个 warning**：`SessionContext` 导出 `useSession` hook（React context 惯用模式），不影响正确性。
4. **`__pycache__` 噪声**：跑 Python 测试会重新生成被跟踪的 `.pyc`，不要 stage/commit。
5. **LF/CRLF 换行警告**：git 提示下次 checkout 会转换换行，提交前应检查 diff，避免整文件换行噪声。
6. **worktree 已过时**：`codex/p7-web-mvp`（`6ff99f0`）仅保留审计轨迹；所有后续开发在主工作区 `main` 进行，勿回 worktree 继续开发。

## 7. 已确定且不应重复推翻的架构/技术决策

- 前端栈固定 React 19 + TypeScript + Vite + npm；Vitest + React Testing Library；React Router v7。
- 后端 Governor 与 Living Brief 是 canonical truth；浏览器只持有 typed UI projection（`FrontendSessionState`）。
- React 组件不直接 `fetch`；所有异步经 typed `BrainstormApi` 边界。
- 仅实现显式标注的 development-only mock；不实现/暗示真实后端/Provider；恒显 “Development simulation”。
- 状态管理用 React context + local state，不引入大型状态库。
- 刷新恢复只经 versioned、allowlisted、non-secret `sessionStorage` projection；storage 不可用安全降级。
- Provider key 用 `EphemeralProviderSecret`，仅驻留 capability screen 组件 state；mock 持久化时显式剥离 `providers`；凭据存在 ≠ 授权（显式授权 checkbox）。
- 四 Idea stage 映射固定：idea→Shape、explore→Spark、solution→Stress、decision→Decide；无第五 mode。
- 六 Frame/canonical 字段固定（Who & Job→target_user/core_task；Desired Change→desired_change；Constraints→hard_constraints；Success→success_metrics；Failure Boundary→abandonment_criteria；Scope & Validation→non_goals/validation_horizon）。
- AI 建议初始 `ASSUMPTION`，仅用户显式确认→`KNOWN`。
- Council Enable 需 ≥2 名称互异且 URL/model/key 合法的 Provider + 调用前显式授权；Skip 是一等结果。
- Formal Handoff 仅 `governorStatus === 'COMMIT'` 渲染。
- 本轮不部署、不配 DNS、不存真实凭据、不 push/merge/建 PR。

## 8. 建议接手顺序（收尾到 `COMMIT`）

1. 用浏览器工具（Playwright / `control-in-app-browser`）跑场景 A–E：标准跳过、`NEEDS_INPUT` 恢复、Council 双 Provider 授权、Provider 失败、刷新恢复。
2. 验证 390/768/1280/1440 视口无横向溢出、键盘可达/激活顺序、可见焦点、标签/错误关联、对比度、reduced motion。
3. React 性能审查 + 最新 Web Interface Guidelines 审查 + 正式安全审查；修复全部 CRITICAL/HIGH 与 P7 violation。
4. 把上述 evidence 写入 `artifacts/acceptance/`，并在 `p7-manifest.json` 将 A1/A9/A10/A11 标记 `pass`、T5→`done`。
5. 重跑 `validate_p7.py`（必须 `valid:true`）、`npm run typecheck/lint/test/build`、P0–P6 tests + regression gate + FV report。
6. 全部 A1–A11 pass 且有 durable evidence，才把 gate 设为 `COMMIT`；否则保持 `DEVELOPING`/`BLOCKED`。

## 9. 不要随意修改的文件/边界

- `artifacts/brainstorm-web-host-v2.p6-handoff.json` 及其 SHA、`artifacts/brainstorm-web-host-v2.approved.json` + `.manifest.json`：P7 authority，不得编辑。
- `BRAINSTORM_WEB_HOST_BRIEF_V2.md` 与 `.trace.json`：P0–P6 审计/状态，不得手改伪造。
- `p7-manifest.json` 的 A1–A11 原文、三个 non-goals、source handoff path/SHA：不可弱化；只能基于真实证据更新 task/status/evidence。
- `.agents/skills/brainstorm-governor/**`、`runtime/**`、`persistence/**`、`observability/**`、`acceptance/**`、`ci/**`：Governor 运行时，非本轮目标。
- `README.md`、`evals/**`、diet-app/council 相关文件：既有用户/他任务改动，勿回退/覆盖/纳入 Web commit。
- `web/src/types/contracts.ts`、`web/src/types/mappings.ts`、`web/src/state/sessionPersistence.ts`、`web/src/api/developmentMock.ts`：已审查边界，增量兼容，非必要勿推翻。
- 不要提交真实 API key、token、credential 或含它们的 fixture/screenshot/log。

## 10. Git 状态快照

### 主工作区 `main`（`git log --oneline`）

```text
45547bc docs(p7): record T5 test/build/security evidence and acceptance status (T5)
c954f96 feat(web): add responsive visual system and accessibility checks (T4)
c7eb070 feat(web): add typed API, development mock, run, capability, human gate, and handoff (T3)
482bc02 feat(web): implement app shell, idea intake, and six-frame wizard (T2)
543bc81 chore(p7): close T1 and open T2 with corrected output paths
902e71c feat(web): add brainstorm web host T1 foundation
3949387 wip: handoff from codex to deepseek
f46e637 首次提交 brainstorm
```

工作树：clean，除 2 个未跟踪 `__pycache__` 噪声项（勿提交）。

### 隔离 worktree `codex/p7-web-mvp`（历史审计，勿再开发）

```text
6ff99f0 docs(p7): freeze frontend contract and TDD implementation plan
bafe715 fix(web): harden storage restore and align node engines
12cd653 fix(web): harden typed session contracts
2f2030d feat(web): add typed Brainstorm foundation
f46e637 首次提交 brainstorm
```
