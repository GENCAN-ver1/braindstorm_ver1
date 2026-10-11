# Brainstorm · Open Storm

让模糊想法通过自由发散、问题风暴和跨分支组合，形成可继续探索的方向。

**默认由你当前打开的 Agent 读取仓库并主持头脑风暴，无需 API key。多角色视角和多模型 Council 均为可选能力。**

目前已具备开放探索、问题追问、点子保存与恢复、分支组合和结果导出的基本能力，可以通过当前 Agent 开始使用。多模型参与的接入口也已提供，填写自己的服务配置后可按需启用；各服务的实际兼容性与使用体验仍在完善。

## 为什么使用

- 一句话即可开始，无需先填写完整 Problem Frame。
- 可以跳转、反转、组合和继续追问，不强制固定阶段或唯一赢家。
- 区分假设与用户陈述，保留问题、不同意见和点子的来路。
- 需要决策时，再使用结构化 Governor 的证据、评估与交付流程。

## 快速开始：使用当前 Agent

在能够读取文件的 Agent 中打开或提供此仓库，然后发送：

```text
请阅读 README.md、AGENTS.md 和 .agents/skills/open-storm/SKILL.md，
使用你当前的模型直接主持头脑风暴，不调用外部模型。
我的主题是：……
```

Agent 会从你的原话开始探索。你可以参与回答、观察发散或选择分支；多角色视角按需加入。没有配置 Council 不影响使用。

宿主 Agent 的模型访问由你已有的客户端、订阅或 API 配置负责，本仓库不要求额外配置模型服务。聊天模型若不能读取仓库，需要由你提供上述文件内容。

### 可选：保存探索过程

如需保存、恢复和导出点子图，使用 Python 3.10+：

```bash
python scripts/brainstorm.py storm init --topic "你的主题" --session staging/my-storm.json
python scripts/brainstorm.py storm prepare --session staging/my-storm.json --role initiator
```

当前 Agent 根据 `prepare` 提示生成内容，再通过 `import` 保存。CLI 负责图和状态，不会在默认模式下另行启动模型。完整命令见 [开放探索指南](docs/OPEN_STORM.md)。

## 可选：多模型 Council

只有你明确选择外部模型参与时才需要此配置。未填写密钥时，继续使用上面的当前 Agent 模式。

1. 将 [.env.example](.env.example) 复制为 `.env`，自行填写所需服务的 key。
2. 将 [模型配置模板](config/open-storm-providers.example.json) 复制为 `config/open-storm.local.json`，填写账户支持的 HTTPS API 地址与模型 ID，将选用的 provider 设为 `enabled: true`。
3. 选择成员并显式运行 Council：

```bash
python scripts/brainstorm.py storm round --session staging/my-storm.json --config config/open-storm.local.json --env-file .env --members ds-venture kimi-affected
```

| 服务 | 本地 key 项 | 接入方式 |
|---|---|---|
| DeepSeek | `DEEPSEEK_API_KEY` | Chat Completions 兼容 API |
| Kimi | `MOONSHOT_API_KEY` | Chat Completions 兼容 API |
| GLM | `GLM_API_KEY` | Chat Completions 兼容 API |
| Qwen | `DASHSCOPE_API_KEY` | Chat Completions 兼容 API |
| OpenAI API（可选） | `OPENAI_API_KEY` | Chat Completions 兼容 API |
| 本机 Codex / ChatGPT 订阅（可选） | 无需额外 key | 显式选择 `openai-outsider` |

`.env` 和本地模型配置被 Git 忽略；不要把 key 写入模板、聊天、运行结果或提交记录。外调会发送所选主题与父节点，并消耗对应账户额度。默认宿主模式不读取 `.env`。

至少两个不同 provider 成功参与，才标记为真实 Council；同一个模型扮演多个角色属于视角模拟。

## 文档与帮助

- [仓库 Agent 启动说明](AGENTS.md)
- [开放探索与 API 配置](docs/OPEN_STORM.md)
- [结构化 Governor 与本地 Web Host](docs/GOVERNOR_GUIDE.md)
- [开发日志](docs/DEVELOPMENT_LOG.md) · [历史验收记录](docs/OPEN_STORM_VERIFICATION.md)
- 问题与反馈：[GitHub Issues](https://github.com/GENCAN-ver1/braindstorm_ver1/issues)

## 贡献与许可

欢迎通过 Issues 分享使用反馈、讨论想法或提交改进。

仓库目前未提供 `LICENSE`；请在复用或分发前向维护者确认许可。
