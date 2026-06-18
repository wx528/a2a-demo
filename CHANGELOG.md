# Changelog

所有 notable 变更都会记录在这个文件里。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

无。

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

[Unreleased]: https://github.com/scott/a2a/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/scott/a2a/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/scott/a2a/releases/tag/v0.2.0
[0.1.0]: https://github.com/scott/a2a/releases/tag/v0.1.0
