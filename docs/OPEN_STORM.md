# Brainstorm v2 · Open Storm

一句话启动探索。角色与模型独立配置；先独立出点，再接力变异、反转、组合或问题风暴。无固定阶段顺序、点子数量或完整 Frame 前置要求。运行时保存模型/用户提出的内容，不以程序模板冒充模型生成。

## 开始

```powershell
python scripts/open_storm.py init --topic "如何重新组织小企业融资" --session staging/my-storm.json
python scripts/open_storm.py prepare --session staging/my-storm.json --role venture --operation expand
```

本机 Codex 阅读 prepare 的 prompt，输出 `{"ideas":[{"text":"具体想法","mechanism":"新增机制"}]}`，将 JSON 保存至新文件后导入：

```powershell
python scripts/open_storm.py import --session staging/my-storm.json --role venture --input my-response.json
python scripts/open_storm.py status --session staging/my-storm.json
```

问题风暴使用 `--operation question`，输出 `{"questions":[{"text":"问题","mechanism":"打开的方向"}]}`。其他动作：`expand`、`mutate`、`combine`、`invert`、`stress`。组合需要至少两个已存在父节点；mutate/stress 需要父节点。

```powershell
python scripts/open_storm.py prepare --session staging/my-storm.json --role bank --operation combine --parents NODE_A NODE_B
python scripts/open_storm.py answer --session staging/my-storm.json --question QUESTION_ID --text "用户的回答"
python scripts/open_storm.py converge --session staging/my-storm.json --select NODE_A NODE_B
python scripts/open_storm.py explore --session staging/my-storm.json
python scripts/open_storm.py export --session staging/my-storm.json --output staging/my-space-map.md
```

`role --id <new-id> --description <利益/资源/知识/盲区>` 添加活动专属角色；prepare/import 的 role 可以使用该 ID。收敛只记录选择，未经过 Governor 审批的结果不可称为已验证决策。

## 五家模型入口

使用 `config/open-storm-providers.example.json` 创建个人配置。模型 IDs 和 API base URLs 默认空；按自己账户能访问的旗舰模型填写，避免把可能过时的名称写死。`base_url` 是 HTTPS API 根地址（通常含版本路径），也可以直接填完整 `/chat/completions` 地址。`options` 可传供应商支持的 token 参数、temperature 和思考参数，不能覆盖 model/messages/stream。

| Provider | 入口 | 凭据 |
|---|---|---|
| deepseek | Chat Completions compatible | DEEPSEEK_API_KEY |
| kimi | Chat Completions compatible | MOONSHOT_API_KEY |
| glm | Chat Completions compatible | GLM_API_KEY |
| qwen | Chat Completions compatible | DASHSCOPE_API_KEY |
| openai | 本机 codex exec / ChatGPT 登录 | 不配置 API key |

成员映射只是示例，可让任何模型扮演任何角色。填写配置并设置对应进程环境变量后，将需要的 provider 设为 `enabled: true`。

```powershell
python scripts/open_storm.py round --session staging/my-storm.json --config MY-CONFIG.json --members ds-venture kimi-affected glm-bank qwen-operator openai-outsider --operation expand
```

只有显式 round 才外调。每个成员只收到主题、自己的立场/动作和选定父节点。先快照所有提示词，再逐个执行，按成员保存结果；不自动重试。至少两个不同 provider 成功时输出 `council: true`。部分失败返回退出码 1，保留成功点子及独立失败事件。pending 事件表示中断时未确认完成，人工判断后再调用，避免自动重复消耗。

OpenAI 启动前可运行 `codex login status`，必须是 ChatGPT 登录。适配器强制 `forced_login_method="chatgpt"` 并去掉 API-key 环境变量，不降级为 API 计费。`model: null` 使用 CLI 默认模型，不能声称这是指定旗舰；需使用旗舰时填写当前本机可用的确切 model ID。额度和模型访问由订阅账户决定。

## 边界与验证

- 本版本提供本地 CLI 与项目技能入口，未改造 Web UI。
- 当前会话文件支持单写者；不要让两个进程同时写同一 session。
- idea/question 默认 ASSUMPTION；用户回答为 USER_STATEMENT，外部事实须在后续研究中验证。
- API 返回必须满足 ideas/questions JSON 合同，错误保留为事件；不以运营失败替代创意。
- 会话使用原子替换保存；init/export 对既有目标拒绝覆盖。
- 外调和 CLI 会消耗对应账户额度；目前不提供供应商价格表或自动挑选旗舰。

```powershell
python -m unittest tests.test_open_storm -v
```
