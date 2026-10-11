# Brainstorm 开发日志

## 2026-10-11 · 文档与启动方式调整

README 改为项目介绍与使用入口；默认由当前宿主 Agent 阅读仓库开展探索。Council 为可选外调能力，密钥填写在本地忽略文件，提供空白模板。

本轮检查：仅检查代码/文档差异与 Git 忽略规则，未运行测试、未外调模型、未更新发布基线。README、AGENTS.md 与密钥读取适配器纳入版本指纹，历史 PASS/ALLOW 不作为本轮验收结论。修改位于原工作目录；本地 main 尚未同步先前已合并的提交，其他业务材料与暂存删除保留。

## 从原 README 迁移的历史记录

以下内容为原 README 的历史记录，不代表当前版本再次通过验收。后续运行证据见 OPEN_STORM_VERIFICATION.md 和 acceptance/。

## 当前状态

仓库已经完成 P0–P6 本地合同，并提供真实 OpenAI-compatible Council 与 Evaluator 的通用适配边界。

| 能力 | 通用合同 | 默认根命令自动接线 | 外部接入边界 |
|---|---:|---:|---|
| P0 路由与状态验证 | 已完成 | 已接线 | 无外部依赖 |
| P1 单 Agent 核心循环 | 已完成 | 已接线 | 无外部依赖 |
| P2 Living Brief 与恢复 | 已完成 | 已接线 | 文件持久化 |
| P3 Challenge Engine | 已完成 | 由结构化核心输入驱动 | 无外部依赖 |
| P4 Research / 引用支持 | 已完成 | 需要宿主 Provider | Provider-neutral 接口 |
| P5 Isolated Workers | 已完成 | 需要宿主 Executor | 隔离执行接口 |
| P5 多模型 Council | 已完成 | 不自动外调 | OpenAI-compatible HTTP 适配器 |
| P6 Evaluator / Trace / Handoff | 已完成 | 不自动外调 | Evaluator、usage、artifact 与 manifest 接口 |
| FV-07 回归发布门 | 已完成 | 独立执行 | 当前结果 `ALLOW` |

`scripts/brainstorm.py` 是通用、安全的单命令入口，当前自动编排 P0/P1/P2，并运行到合法停止状态。P4/P5/P6 提供通用合同和适配器，由宿主在通过配置、门禁和用户授权后显式接入；根命令不会自动发起网络调用。

### 本阶段沉淀的通用改进

- Council 从“仅有合同”扩展为可接入真实 OpenAI-compatible Provider 的通用 HTTP 适配器，同时保留 Provider 隔离、成功数门槛和多 Provider 独立性校验。
- Evaluator 增加真实 Provider 适配器，并由 `TracedEvaluator` 统一执行轮次上限、请求预留、receipt 复用和实际 usage 记录。
- 密钥可用不代表获得数据发送授权；外调前必须明确共享字段、接收方和用途，并将返回内容一律视为 `DATA_ONLY`。
- 外部结果必须先进入 staging，经过 Schema、引用、冲突和归一化校验后，才能由主 Agent 以 copy-on-write 方式提交。
- 场景或项目专属的请求、证据、配置与产物不属于 Governor 根合同；根 README 只记录可复用机制和通用使用方式。


## 历史验收记录

本阶段已验证：

- FV-07：`ALLOW`
- 离线合同：108 项通过
- Live Report：已接受
- Full Version：`PASS`
