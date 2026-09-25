# Changelog

所有 notable 变更都会记录在这个文件里。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Fixed

- `research-agent` 流式输出中途失败不再静默截断：异常上抛，任务正确落 `TASK_STATE_FAILED`
- 辩论 Agent system prompt 增加提示注入防护：检索资料与对手论点均声明为数据而非指令
- 双语 README 辩论章节补充转录示例（展示引用标注与"未查证推演"声明格式）

### Added

- A2A 一致性套件 `evals/conformance/`：11 项协议检查对任意 agent 打分（CLI + JSON 报告），CI 每次 push 对 research/debate agent 自动运行
- 辩论质量评测 `evals/quality/`：15 题辩题集（含 3 道错误前提陷阱题）、引用覆盖率/链接存活率确定性指标、论断支持率/人格保持度 LLM-as-judge、独立裁判（`JUDGE_*` 回退 `LLM_*` 并标注自评）、JSON+Markdown 报告；GitHub Actions `Eval` 工作流手动触发
- GitHub Actions CI（`.github/workflows/ci.yml`）：ruff + 单元/端到端/Web 集成测试，每次 push/PR 运行，离线不消耗 LLM 额度
- LLM 真实链路冒烟测试（`test_llm_smoke.py` + `.github/workflows/llm-smoke.yml`）：push main 或手动触发，验证非回退输出、token 级流式与 orchestrator 工作流；默认 DeepSeek（`deepseek-chat`），key 走仓库 Secret `LLM_API_KEY`，无 key 本地自动跳过

- Orchestrator 动态发现：启动时通过 `/.well-known/agent-card.json` 拉取 Agent Card 自动注册（`AGENT_URLS` 环境变量，逗号分隔），支持按 card 名称 / 短名 / skill id 解析，`POST /agents/refresh` 可运行时重新发现，无需重启；旧版成对 URL 环境变量保留为回退
- 真流式输出：`A2AJSONRPCServer` 新增可选 `process_task_stream` 生成器参数，`SendStreamingMessage` 通过线程 + 队列桥接逐块推送 `TaskArtifactUpdateEvent`（`append` / `lastChunk` 语义，单一 `artifactId`）；新增 `call_llm_stream` 流式 LLM 客户端；`research-agent` 已接入（card 声明 `streaming: true`），`writing-agent` 保持非流式以示范能力协商
- SQLite 任务持久化：新增 `SqliteTaskStore`（write-through + 重启加载），设置 `TASK_DB` 环境变量即启用；docker compose 为两个 agent 挂载 named volume 并默认开启
- 人格辩论 Demo：`debate-agent`（检索资料 + 引用论证，无资料明说绝不编造）与 CLI 编排器 `debate/run_debate.py`（苏格拉底/休谟/康德/尼采/怀疑论工程师/风险投资人 + 中立裁判，多轮对抗 + 判定）
- 搜索工具层 `shared/search_tool.py`：默认 DuckDuckGo 免 key，可选 Tavily（`SEARCH_PROVIDER`/`SEARCH_API_KEY`），任何失败降级为空结果
- docker-compose 新增 `debate-agent` 服务（8003 端口，SQLite 持久化卷）

### Fixed

- 任务失败兜底：`process_task` 抛异常时任务自动落入 `TASK_STATE_FAILED`（状态消息包含错误原因），不再卡在 `WORKING`；同步、异步（`returnImmediately`）与 SSE 流式三条执行路径均已覆盖
- 多轮会话（任务续聊）：`SendMessage` 消息携带 `taskId` 且任务处于非终态时，向既有任务追加用户消息并继续处理，复用同一 task
- 上下文续聊：消息仅携带 `contextId` 时创建新任务，并自动继承该上下文最近任务的对话历史（上限 20 条），实现跨任务会话记忆
- 终态任务（`TASK_STATE_COMPLETED` / `FAILED` / `CANCELED` / `REJECTED`）再收消息时返回规范错误 `-32004` `UnsupportedOperationError`，而非静默创建新任务

## [0.4.0] - 2026-09-26

### Changed

- 对齐 A2A v1.0.0 规范的 JSON-RPC 方法名：`tasks/send` → `SendMessage`、`tasks/get` → `GetTask`、`tasks/cancel` → `CancelTask`、`tasks/list` → `ListTasks`、`tasks/sendSubscribe` → `SendStreamingMessage`、`tasks/subscribe` → `SubscribeToTask`（旧方法名保留为兼容别名）
- Agent Card 发现路径改为规范的 `/.well-known/agent-card.json`（旧路径 `agent.json` 保留为兼容别名）
- 枚举值对齐规范：TaskState 改为 `TASK_STATE_*`、Role 改为 `ROLE_USER` / `ROLE_AGENT`（SCREAMING_SNAKE_CASE）；服务端输入兼容 v0.x 小写旧值，输出一律新值
- JSON-RPC 错误对齐规范：`error.data` 改为 ProtoJSON Any 数组，包含 `google.rpc.ErrorInfo`（`reason` / `domain: a2a-protocol.org`）；错误码对齐规范映射（`TaskNotFoundError` → `-32001`、`TaskNotCancelableError` → `-32002`）
- 时间戳对齐规范：`TaskStatus.timestamp` 使用毫秒精度（`YYYY-MM-DDTHH:mm:ss.sssZ`）

### Fixed

- 修复 `SendMessage`（原 `tasks/send`）同步执行 `process_task` 阻塞 FastAPI 事件循环的问题：改为 `asyncio.to_thread` 执行，LLM 慢调用期间服务保持响应
- `A2AJSONRPCClient.fetch_agent_card` 优先请求规范路径 `agent-card.json`，失败时回退旧路径

## [0.2.1] - 2026-06-18

### Added

- Web 会议室支持 Markdown 渲染与 fenced code block 代码高亮

### Fixed

- 修复 `@babel/standalone` automatic JSX runtime 导致页面无法渲染的问题
- 修复圆桌/流水线模式下 Moderator、Code、Review 等 Agent 把角色提示词泄漏到会议室消息中的问题
- 将 `research-agent` / `writing-agent` 改为通用指令跟随 Agent，角色特定指令由调用方（Orchestrator / Web）提供

## [0.3.0] - 2026-06-18

### Added

- 核心数据模型全面对齐 A2A v1.0 规范（TaskStatus、Part、Message、Artifact、AgentCard 等）
- Agent Server 改为 JSON-RPC 2.0 绑定，统一入口 `POST /rpc`
- Agent Card 新增 `supportedInterfaces`，声明协议绑定、版本与 RPC 入口地址
- Orchestrator 改为 A2A JSON-RPC 2.0 客户端调用远端 Agent
- 新增 `tasks/send`、`tasks/get`、`tasks/cancel`、`tasks/list` 等 JSON-RPC 方法
- 新增 `POST /rpc/stream` SSE 流式入口，支持 `tasks/sendSubscribe` 与 `tasks/subscribe`
- 新增 `test_a2a.py`（TestClient 单元测试）与 `test_e2e.py`（真实端口端到端测试）
- 为旧版 Web 会议室保留 `TextPart` / `TaskSendParams` 等向后兼容别名
- Web 会议室新增「圆桌讨论模式（Roundtable）」：由 Moderator 主持，支持多轮自由讨论
- 新增 `moderator` 主持人 Agent：负责开场、控制发言顺序、总结讨论
- 每个 Agent 在圆桌模式下可以听到其他 Agent 的发言，并自主决定是否参与讨论（支持 PASS）
- 创建会议室时可通过前端下拉菜单选择「流水线模式」或「圆桌讨论模式」
- 圆桌讨论模式支持选择 1-10 轮，前端提供滑块控件
- 第一轮强制 Research、Writing Agent 发言，确保圆桌讨论有足够基础观点
- Web 会议室新增左侧「会议列表」侧边栏，支持查看历史会议、切换会话、删除会话
- 新增 SQLite 持久化：`web/db.py` 保存会议、参与者、消息，服务重启后会议不丢失
- 新增 `GET /api/meetings` 列表接口与 `DELETE /api/meetings/{id}` 删除接口
- 支持通过 URL 参数 `?meeting={id}` 直接打开指定会议，刷新页面或复制链接均可恢复会话

### Changed

- Agent 返回的结果从 `Task.messages` 迁移到 `Task.artifacts`，符合 A2A 规范
- Task 状态由字符串改为 `TaskStatus` 对象（含 state / message / timestamp）
- 使用 `sessionId` 改为规范中的 `contextId`
- 补充完整 Task 生命周期状态：`submitted`、`working`、`completed`、`failed`、`canceled`、`input-required`、`rejected`、`auth-required`
- README 中的 curl 示例更新为 JSON-RPC 格式
- Web 会议室（`web/main.py`）改为通过 A2A JSON-RPC 调用 `research-agent` / `writing-agent`，不再直接调用 LLM
- 保留原有「流水线模式（Pipeline）」，作为默认模式继续可用
- 优化上下文长度控制，避免长讨论超出 LLM 上下文限制
- 优化圆桌讨论流程：移除主持人对每个 Agent 的单独决策调用，改为 Agent 自我判断是否 PASS，减少约 50% LLM 调用
- 修复圆桌模式下 Writing、Code、Review 等 Agent 输出被截断的问题，按角色分配合理的 `max_tokens`
- 限制圆桌模式下单次 Agent 发言长度，降低多轮讨论耗时和上下文膨胀
- `.gitignore` 忽略 `data/` 目录（SQLite 数据库文件）

## [0.1.0] - 2026-06-15

### Added

- 初始版本发布
- 实现基于 A2A 协议的 Agent Swarm 架构
- 添加 `research-agent`：研究型 Agent，对主题生成摘要
- 添加 `writing-agent`：写作型 Agent，基于摘要生成 Markdown 文章
- 添加 `orchestrator`：编排器，串联多个 Agent 完成任务
- 添加通用 LLM 客户端，支持 OpenAI 兼容 API（OpenAI、DeepSeek、SiliconFlow、Ollama 等）
- 使用 `uv` 进行 Python 依赖管理
- 添加 Docker Compose 部署支持
- 添加 `.env.example` 环境变量示例
- 添加 Web 会议室演示界面（FastAPI + React + SSE）
- Web 会议室中集成 5 个 Agent：Research、Writing、Review、Code、Summary
- 支持 Agent 之间共享完整会议上下文
- 添加 `README.md` 项目文档
- 添加 `CHANGELOG.md`

[Unreleased]: https://github.com/wx528/a2a-demo/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/wx528/a2a-demo/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/wx528/a2a-demo/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/wx528/a2a-demo/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/wx528/a2a-demo/compare/v0.1.1...v0.2.0
[0.1.0]: https://github.com/wx528/a2a-demo/releases/tag/v0.1.0
